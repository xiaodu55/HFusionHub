package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.BidProjectCreateDTO;
import com.hfusionhub.dto.BidProjectDetailDTO;
import com.hfusionhub.dto.BidProjectInfoDTO;
import com.hfusionhub.dto.BidProjectQueryDTO;
import com.hfusionhub.entity.BidProject;
import com.hfusionhub.entity.BidRequirement;
import com.hfusionhub.entity.BidScoringMethod;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.TenderElement;
import com.hfusionhub.mapper.BidProjectMapper;
import com.hfusionhub.mapper.BidRequirementMapper;
import com.hfusionhub.mapper.BidScoringMethodMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.TenderElementMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.BidPlanGateService;
import com.hfusionhub.service.BidProjectService;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/**
 * 投标项目服务实现（招投标垂直化）
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class BidProjectServiceImpl implements BidProjectService {

    /** 低置信阈值：低于该值的需求要素强制人工确认 */
    private static final double LOW_CONFIDENCE = 0.6;

    private static final Set<String> VALID_STATUSES =
            Set.of(
                    BidProject.STATUS_INTERPRETING,
                    BidProject.STATUS_REQUIREMENTS,
                    BidProject.STATUS_DRAFTING,
                    BidProject.STATUS_CHECKING,
                    BidProject.STATUS_SUBMITTED,
                    BidProject.STATUS_ARCHIVED);

    private static final Set<String> VALID_REQUIREMENT_STATUSES =
            Set.of(
                    BidRequirement.STATUS_PENDING,
                    BidRequirement.STATUS_DRAFTING,
                    BidRequirement.STATUS_CHECKED,
                    BidRequirement.STATUS_MANUAL_REVIEW);

    private final BidProjectMapper bidProjectMapper;
    private final TenderElementMapper tenderElementMapper;
    private final BidScoringMethodMapper bidScoringMethodMapper;
    private final BidRequirementMapper bidRequirementMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final JwtUtils jwtUtils;
    private final AiClient aiClient;
    private final ObjectMapper objectMapper;
    private final UsageLedgerService usageLedgerService;
    private final BidPlanGateService bidPlanGateService;

    @Override
    @Transactional
    public BidProjectInfoDTO create(BidProjectCreateDTO createDTO) {
        Long userId = jwtUtils.getCurrentUserId();

        // 校验招标文件知识库存在且归当前用户所有
        KnowledgeBase kb = knowledgeBaseMapper.selectById(createDTO.getKnowledgeBaseId());
        if (kb == null) {
            throw new BusinessException(StatusCode.KNOWLEDGE_BASE_NOT_FOUND, "招标文件知识库不存在");
        }
        if (!kb.getUserId().equals(userId)) {
            throw new BusinessException(StatusCode.FORBIDDEN, "无权使用该知识库");
        }

        // 商业化：三档计费之一「按坐席」——套餐 max_seats 上限校验（P2-7）
        bidPlanGateService.requireSeatAvailable(TenantContext.requireTenantId());

        BidProject project = new BidProject();
        project.setKnowledgeBaseId(createDTO.getKnowledgeBaseId());
        project.setTitle(createDTO.getTitle());
        project.setTenderNumber(createDTO.getTenderNumber());
        project.setBudget(createDTO.getBudget());
        project.setDeadline(createDTO.getDeadline());
        project.setBidBond(createDTO.getBidBond());
        project.setOpeningDate(createDTO.getOpeningDate());
        project.setStatus(BidProject.STATUS_INTERPRETING);
        project.setCreatedBy(userId);

        bidProjectMapper.insert(project);

        // 商业化骨架：投标项目数计量（P0-7），超额则抛 QUOTA_EXCEEDED 回滚创建
        String reservationKey = "bid-project:" + project.getId();
        usageLedgerService.reserve(UsageMeter.BID_PROJECTS, reservationKey, 1, "bid_project",
                String.valueOf(project.getId()));
        usageLedgerService.settle(UsageMeter.BID_PROJECTS, reservationKey, 1, "bid_project",
                String.valueOf(project.getId()));

        log.info("投标项目创建成功，id: {}, title: {}", project.getId(), project.getTitle());
        return convertToInfoDTO(project);
    }

    @Override
    public BidProjectInfoDTO getById(Long id) {
        return convertToInfoDTO(requireOwnedProject(id));
    }

    @Override
    public BidProjectDetailDTO getDetail(Long id) {
        BidProject project = requireOwnedProject(id);

        List<TenderElement> elements = tenderElementMapper.selectList(
                new LambdaQueryWrapper<TenderElement>().eq(TenderElement::getProjectId, id));
        List<BidScoringMethod> scoringMethods = bidScoringMethodMapper.selectList(
                new LambdaQueryWrapper<BidScoringMethod>().eq(BidScoringMethod::getProjectId, id));
        List<BidRequirement> requirements = bidRequirementMapper.selectList(
                new LambdaQueryWrapper<BidRequirement>().eq(BidRequirement::getProjectId, id));

        return BidProjectDetailDTO.builder()
                .project(convertToInfoDTO(project))
                .elements(elements)
                .scoringMethods(scoringMethods)
                .requirements(requirements)
                .build();
    }

    @Override
    public PageResult<BidProjectInfoDTO> list(BidProjectQueryDTO queryDTO) {
        queryDTO.validate();
        Long userId = jwtUtils.getCurrentUserId();

        LambdaQueryWrapper<BidProject> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(BidProject::getCreatedBy, userId);
        if (StringUtils.hasText(queryDTO.getKeyword())) {
            String keyword = queryDTO.getKeyword().trim();
            wrapper.and(w -> w.like(BidProject::getTitle, keyword)
                    .or()
                    .like(BidProject::getTenderNumber, keyword));
        }
        if (StringUtils.hasText(queryDTO.getStatus())) {
            wrapper.eq(BidProject::getStatus, queryDTO.getStatus());
        }
        wrapper.orderByDesc(BidProject::getCreatedAt);

        Page<BidProject> page = new Page<>(queryDTO.getPage(), queryDTO.getPageSize());
        Page<BidProject> result = bidProjectMapper.selectPage(page, wrapper);

        // 批量预加载需求数量（避免 N+1）
        List<Long> ids = result.getRecords().stream().map(BidProject::getId).collect(Collectors.toList());
        Map<Long, Long> reqCountMap = Map.of();
        if (!ids.isEmpty()) {
            List<BidRequirement> reqs = bidRequirementMapper.selectList(
                    new LambdaQueryWrapper<BidRequirement>()
                            .in(BidRequirement::getProjectId, ids)
                            .select(BidRequirement::getProjectId));
            reqCountMap = reqs.stream().collect(Collectors.groupingBy(BidRequirement::getProjectId, Collectors.counting()));
        }

        final Map<Long, Long> finalReqCountMap = reqCountMap;
        List<BidProjectInfoDTO> records = result.getRecords().stream()
                .map(p -> {
                    BidProjectInfoDTO dto = convertToInfoDTO(p);
                    dto.setRequirementCount(finalReqCountMap.getOrDefault(p.getId(), 0L).intValue());
                    return dto;
                })
                .collect(Collectors.toList());
        return PageResult.of(result.getCurrent(), result.getSize(), result.getTotal(), records);
    }

    @Override
    @Transactional
    public void delete(Long id) {
        BidProject project = requireOwnedProject(id);
        bidProjectMapper.deleteById(project.getId());
        log.info("投标项目已删除（软删除），id: {}", id);
    }

    @Override
    public BidProjectInfoDTO updateStatus(Long id, String status) {
        if (!VALID_STATUSES.contains(status)) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "非法的项目状态：" + status);
        }
        BidProject project = requireOwnedProject(id);
        project.setStatus(status);
        bidProjectMapper.updateById(project);
        return convertToInfoDTO(project);
    }

    @Override
    @Transactional
    public BidProjectDetailDTO interpret(Long id) {
        BidProject project = requireOwnedProject(id);

        // 1. 置为解读中
        project.setStatus(BidProject.STATUS_INTERPRETING);
        bidProjectMapper.updateById(project);

        // 2. 调用 Python 解读工作流
        Map<String, Object> result = aiClient.bidInterpret(
                project.getId(), project.getKnowledgeBaseId(), project.getTitle(), project.getTenderNumber());
        if (!"ok".equals(result.get("status"))) {
            throw new BusinessException(
                    StatusCode.SERVICE_UNAVAILABLE,
                    result.get("message") != null ? String.valueOf(result.get("message")) : "解读失败，请稍后重试");
        }

        // 3. 幂等落库：清空旧结果后写入
        tenderElementMapper.delete(
                new LambdaQueryWrapper<TenderElement>().eq(TenderElement::getProjectId, id));
        bidScoringMethodMapper.delete(
                new LambdaQueryWrapper<BidScoringMethod>().eq(BidScoringMethod::getProjectId, id));
        bidRequirementMapper.delete(
                new LambdaQueryWrapper<BidRequirement>().eq(BidRequirement::getProjectId, id));

        persistElements(project.getId(), result.get("elements"));
        persistScoringMethods(project.getId(), result.get("scoring_methods"));
        persistRequirements(project.getId(), result.get("requirements"));

        // 商业化骨架：招标解读要素计量（P0-7），按要素 + 需求项总数计；超额回滚整个解读
        int elementsCount = result.get("elements") instanceof List ? ((List<?>) result.get("elements")).size() : 0;
        int requirementsCount =
                result.get("requirements") instanceof List ? ((List<?>) result.get("requirements")).size() : 0;
        long meterAmount = elementsCount + requirementsCount;
        if (meterAmount > 0) {
            String reservationKey = "bid-interpret:" + id;
            usageLedgerService.reserve(UsageMeter.TENDER_ELEMENTS, reservationKey, meterAmount, "bid_project",
                    String.valueOf(id));
            usageLedgerService.settle(UsageMeter.TENDER_ELEMENTS, reservationKey, meterAmount, "bid_project",
                    String.valueOf(id));
        }

        // 4. 置为需求确认阶段
        project.setStatus(BidProject.STATUS_REQUIREMENTS);
        bidProjectMapper.updateById(project);

        log.info("投标项目解读完成，id: {}, 需求数: {}", id, result.get("requirements") != null ? ((List<?>) result.get("requirements")).size() : 0);
        return getDetail(id);
    }

    @Override
    public void updateRequirementStatus(Long id, Long requirementId, String status) {
        if (!VALID_REQUIREMENT_STATUSES.contains(status)) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "非法的需求状态：" + status);
        }
        requireOwnedProject(id);
        BidRequirement requirement = bidRequirementMapper.selectById(requirementId);
        if (requirement == null || !requirement.getProjectId().equals(id)) {
            throw new BusinessException(StatusCode.NOT_FOUND, "需求不存在");
        }
        requirement.setSatisfiedStatus(status);
        bidRequirementMapper.updateById(requirement);
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

    @SuppressWarnings("unchecked")
    private void persistElements(Long projectId, Object raw) {
        if (!(raw instanceof List)) {
            return;
        }
        for (Object item : (List<Object>) raw) {
            if (!(item instanceof Map)) {
                continue;
            }
            Map<String, Object> m = (Map<String, Object>) item;
            TenderElement element = new TenderElement();
            element.setProjectId(projectId);
            element.setElementKey(asString(m.get("element_key")));
            element.setElementValue(jsonOrNull(m.get("element_value")));
            element.setEvidenceChunkIds(jsonOrNull(m.get("evidence_chunk_ids")));
            element.setConfidence(asBigDecimal(m.get("confidence")));
            element.setSourceClause(asString(m.get("source_clause")));
            if (element.getElementKey() == null) {
                continue;
            }
            tenderElementMapper.insert(element);
        }
    }

    @SuppressWarnings("unchecked")
    private void persistScoringMethods(Long projectId, Object raw) {
        if (!(raw instanceof List)) {
            return;
        }
        for (Object item : (List<Object>) raw) {
            if (!(item instanceof Map)) {
                continue;
            }
            Map<String, Object> m = (Map<String, Object>) item;
            BidScoringMethod method = new BidScoringMethod();
            method.setProjectId(projectId);
            method.setMethodType(asString(m.get("method_type")));
            method.setPointsJson(jsonOrNull(m.get("points_json")));
            method.setTotalScore(asBigDecimal(m.get("total_score")));
            bidScoringMethodMapper.insert(method);
        }
    }

    @SuppressWarnings("unchecked")
    private void persistRequirements(Long projectId, Object raw) {
        if (!(raw instanceof List)) {
            return;
        }
        for (Object item : (List<Object>) raw) {
            if (!(item instanceof Map)) {
                continue;
            }
            Map<String, Object> m = (Map<String, Object>) item;
            BidRequirement requirement = new BidRequirement();
            requirement.setProjectId(projectId);
            requirement.setCategory(asString(m.get("category")));
            requirement.setRequirement(asString(m.get("requirement")));
            requirement.setSourceClause(asString(m.get("source_clause")));
            // 低置信需求强制人工确认（P0-8 风险兜底）
            BigDecimal confidence = asBigDecimal(m.get("confidence"));
            boolean lowConfidence = confidence != null && confidence.doubleValue() < LOW_CONFIDENCE;
            requirement.setSatisfiedStatus(lowConfidence ? BidRequirement.STATUS_MANUAL_REVIEW : BidRequirement.STATUS_PENDING);
            if (requirement.getRequirement() == null) {
                continue;
            }
            bidRequirementMapper.insert(requirement);
        }
    }

    private String asString(Object value) {
        if (value == null) {
            return null;
        }
        return String.valueOf(value);
    }

    private BigDecimal asBigDecimal(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number) {
            return new BigDecimal(value.toString());
        }
        try {
            return new BigDecimal(String.valueOf(value));
        } catch (NumberFormatException e) {
            return null;
        }
    }

    /** 非标量（列表/对象）序列化为 JSON 字符串，标量原样输出 */
    private String jsonOrNull(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof String || value instanceof Number || value instanceof Boolean) {
            return String.valueOf(value);
        }
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception e) {
            log.warn("字段序列化失败: {}", e.getMessage());
            return String.valueOf(value);
        }
    }

    private BidProjectInfoDTO convertToInfoDTO(BidProject project) {
        return BidProjectInfoDTO.builder()
                .id(project.getId())
                .knowledgeBaseId(project.getKnowledgeBaseId())
                .tenderNumber(project.getTenderNumber())
                .title(project.getTitle())
                .budget(project.getBudget())
                .deadline(project.getDeadline())
                .bidBond(project.getBidBond())
                .openingDate(project.getOpeningDate())
                .status(project.getStatus())
                .createdBy(project.getCreatedBy())
                .createdAt(project.getCreatedAt())
                .updatedAt(project.getUpdatedAt())
                .build();
    }
}
