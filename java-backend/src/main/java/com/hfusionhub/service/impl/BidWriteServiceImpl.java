package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.BidDraft;
import com.hfusionhub.entity.BidProject;
import com.hfusionhub.entity.BidRequirement;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.BidDraftMapper;
import com.hfusionhub.mapper.BidProjectMapper;
import com.hfusionhub.mapper.BidRequirementMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.BidWriteService;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 标书撰写服务实现（招投标垂直化 · P1）
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class BidWriteServiceImpl implements BidWriteService {

    private static final Set<String> VALID_DRAFT_STATUSES =
            Set.of(BidDraft.STATUS_APPROVED, BidDraft.STATUS_REJECTED);

    private final BidProjectMapper bidProjectMapper;
    private final BidRequirementMapper bidRequirementMapper;
    private final BidDraftMapper bidDraftMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final JwtUtils jwtUtils;
    private final AiClient aiClient;
    private final UsageLedgerService usageLedgerService;
    private final ObjectMapper objectMapper;

    @Override
    @Transactional
    public List<BidDraft> write(Long projectId) {
        BidProject project = requireOwnedProject(projectId);

        List<Map<String, Object>> requirements = loadRequirements(projectId);
        List<Long> kbIds = loadKnowledgeBaseIds(project);
        Map<String, Object> result = aiClient.bidWrite(
                projectId, project.getTitle(), project.getTenderNumber(), kbIds, requirements, null);
        if (!"ok".equals(result.get("status"))) {
            throw new BusinessException(
                    StatusCode.SERVICE_UNAVAILABLE,
                    result.get("message") != null ? String.valueOf(result.get("message")) : "撰写失败，请稍后重试");
        }

        Long userId = jwtUtils.getCurrentUserId();
        List<BidDraft> drafts = persistSections(projectId, result.get("sections"), userId);
        meterDraftChars(projectId, drafts);
        project.setStatus(BidProject.STATUS_DRAFTING);
        bidProjectMapper.updateById(project);
        log.info("标书撰写完成（同步），projectId: {}, 分节数: {}", projectId, drafts.size());
        return drafts;
    }

    @Override
    public void writeStream(Long projectId, SseEmitter emitter) {
        BidProject project = requireOwnedProject(projectId);
        final Long streamTenantId = TenantContext.requireTenantId();

        List<Map<String, Object>> requirements = loadRequirements(projectId);
        List<Long> kbIds = loadKnowledgeBaseIds(project);
        // 请求线程捕获用户/租户上下文，供 Reactor 回调落库使用
        final Long userId = jwtUtils.getCurrentUserId();
        var flux = aiClient.bidWriteStream(
                projectId, project.getTitle(), project.getTenderNumber(), kbIds, requirements, null);
        AtomicBoolean persisted = new AtomicBoolean(false);

        flux.subscribe(
                chunk -> {
                    TenantContext.runAs(streamTenantId, () -> {
                        try {
                            String line = chunk.trim();
                            if (line.isEmpty()) {
                                return;
                            }
                            String json = line.startsWith("data:") ? line.substring(5).trim() : line;
                            if (json.isEmpty() || "[DONE]".equals(json)) {
                                return;
                            }
                            Map<String, Object> event = objectMapper.readValue(json, Map.class);
                            emitter.send(SseEmitter.event().data(event, MediaType.APPLICATION_JSON));
                            if ("run_completed".equals(event.get("event")) && persisted.compareAndSet(false, true)) {
                                List<BidDraft> drafts = persistSections(projectId, event.get("sections"), userId);
                                meterDraftChars(projectId, drafts);
                                TenantContext.runAs(streamTenantId, () -> {
                                    BidProject p = bidProjectMapper.selectById(projectId);
                                    if (p != null) {
                                        p.setStatus(BidProject.STATUS_DRAFTING);
                                        bidProjectMapper.updateById(p);
                                    }
                                });
                                log.info("标书撰写完成（流式），projectId: {}, 分节数: {}", projectId, drafts.size());
                            }
                        } catch (Exception e) {
                            log.warn("Bid write stream relay failed: {}", e.getMessage());
                            emitter.completeWithError(e);
                        }
                    });
                },
                error -> {
                    log.warn("Bid write stream error: {}", error.getMessage());
                    try {
                        emitter.send(SseEmitter.event()
                                .data(Map.of("event", "run_error", "error_detail", String.valueOf(error.getMessage()))));
                    } catch (Exception ignored) {
                        // 前端已断开
                    }
                    emitter.complete();
                },
                emitter::complete);
    }

    @Override
    public List<BidDraft> listDrafts(Long projectId) {
        requireOwnedProject(projectId);
        return bidDraftMapper.selectList(new LambdaQueryWrapper<BidDraft>()
                .eq(BidDraft::getProjectId, projectId)
                .orderByDesc(BidDraft::getVersion)
                .orderByAsc(BidDraft::getSectionKey));
    }

    @Override
    @Transactional
    public void updateDraftStatus(Long draftId, String status) {
        if (!VALID_DRAFT_STATUSES.contains(status)) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "非法的分节状态：" + status);
        }
        BidDraft draft = bidDraftMapper.selectById(draftId);
        if (draft == null) {
            throw new BusinessException(StatusCode.NOT_FOUND, "分节草稿不存在");
        }
        requireOwnedProject(draft.getProjectId());
        draft.setStatus(status);
        if (BidDraft.STATUS_APPROVED.equals(status)) {
            draft.setApprovedBy(jwtUtils.getCurrentUserId());
        }
        bidDraftMapper.updateById(draft);
        log.info("标书分节状态更新，draftId: {}, status: {}", draftId, status);
    }

    // ── 私有方法 ────────────────────────────────────────────────

    private BidProject requireOwnedProject(Long id) {
        BidProject project = bidProjectMapper.selectById(id);
        if (project == null) {
            throw new BusinessException(StatusCode.BID_PROJECT_NOT_FOUND, "投标项目不存在");
        }
        if (!project.getCreatedBy().equals(jwtUtils.getCurrentUserId())) {
            throw new BusinessException(StatusCode.FORBIDDEN, "无权操作此投标项目");
        }
        return project;
    }

    /**
     * 撰写检索范围 = 招标文件库 + 项目创建者的资质库/历史标书库（P1-6）。
     * 让撰写工作流自动检索复用企业资质与历史标书，多 KB 检索由 Python 侧按 chunk 去重。
     */
    private List<Long> loadKnowledgeBaseIds(BidProject project) {
        List<Long> ids = new ArrayList<>();
        if (project.getKnowledgeBaseId() != null) {
            ids.add(project.getKnowledgeBaseId());
        }
        Long ownerId = project.getCreatedBy();
        if (ownerId == null) {
            return ids;
        }
        for (String category : List.of(KnowledgeBase.CATEGORY_QUALIFICATION, KnowledgeBase.CATEGORY_BID_HISTORY)) {
            knowledgeBaseMapper.selectList(new LambdaQueryWrapper<KnowledgeBase>()
                            .eq(KnowledgeBase::getUserId, ownerId)
                            .eq(KnowledgeBase::getCategory, category)
                            .eq(KnowledgeBase::getStatus, KnowledgeBase.STATUS_NORMAL))
                    .forEach(kb -> {
                        if (!ids.contains(kb.getId())) {
                            ids.add(kb.getId());
                        }
                    });
        }
        return ids;
    }

    private List<Map<String, Object>> loadRequirements(Long projectId) {
        List<BidRequirement> requirements = bidRequirementMapper.selectList(
                new LambdaQueryWrapper<BidRequirement>()
                        .eq(BidRequirement::getProjectId, projectId)
                        .orderByAsc(BidRequirement::getId));
        List<Map<String, Object>> maps = new ArrayList<>();
        for (BidRequirement req : requirements) {
            Map<String, Object> map = new HashMap<>();
            map.put("category", req.getCategory());
            map.put("requirement", req.getRequirement());
            map.put("source_clause", req.getSourceClause());
            maps.add(map);
        }
        return maps;
    }

    @SuppressWarnings("unchecked")
    private List<BidDraft> persistSections(Long projectId, Object raw, Long userId) {
        List<BidDraft> drafts = new ArrayList<>();
        if (!(raw instanceof List)) {
            return drafts;
        }
        for (Object item : (List<Object>) raw) {
            if (!(item instanceof Map)) {
                continue;
            }
            Map<String, Object> m = (Map<String, Object>) item;
            String sectionKey = asString(m.get("section_key"));
            String content = asString(m.get("content"));
            if (sectionKey == null || content == null) {
                continue;
            }
            String sectionTitle = asString(m.get("section_title"));
            // 幂等覆盖：按 project+section 取最新版本，重写则版本 +1
            BidDraft existing = bidDraftMapper.selectOne(new LambdaQueryWrapper<BidDraft>()
                    .eq(BidDraft::getProjectId, projectId)
                    .eq(BidDraft::getSectionKey, sectionKey)
                    .orderByDesc(BidDraft::getVersion)
                    .last("LIMIT 1"));
            BidDraft draft = new BidDraft();
            draft.setProjectId(projectId);
            draft.setSectionKey(sectionKey);
            draft.setSectionTitle(sectionTitle);
            draft.setContent(content);
            draft.setStatus(BidDraft.STATUS_DRAFTING);
            draft.setVersion(existing == null ? 1 : existing.getVersion() + 1);
            draft.setCreatedBy(userId);
            if (existing != null) {
                draft.setId(existing.getId());
                bidDraftMapper.updateById(draft);
            } else {
                bidDraftMapper.insert(draft);
            }
            drafts.add(draft);
        }
        return drafts;
    }

    /** 计量：标书撰写字符数（P1-7），超额抛 QUOTA_EXCEEDED 回滚本次撰写 */
    private void meterDraftChars(Long projectId, List<BidDraft> drafts) {
        int chars = drafts.stream()
                .mapToInt(d -> d.getContent() == null ? 0 : d.getContent().length())
                .sum();
        if (chars <= 0) {
            return;
        }
        String key = "bid-draft:" + projectId;
        usageLedgerService.reserve(UsageMeter.BID_DRAFT_CHARS, key, chars, "bid_project",
                String.valueOf(projectId));
        usageLedgerService.settle(UsageMeter.BID_DRAFT_CHARS, key, chars, "bid_project",
                String.valueOf(projectId));
    }

    private String asString(Object value) {
        if (value == null) {
            return null;
        }
        return String.valueOf(value);
    }
}
