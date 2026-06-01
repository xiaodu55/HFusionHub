package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.BidCheckReport;
import com.hfusionhub.entity.BidDraft;
import com.hfusionhub.entity.BidProject;
import com.hfusionhub.entity.BidRequirement;
import com.hfusionhub.entity.BidSubscription;
import com.hfusionhub.mapper.BidCheckReportMapper;
import com.hfusionhub.mapper.BidDraftMapper;
import com.hfusionhub.mapper.BidProjectMapper;
import com.hfusionhub.mapper.BidRequirementMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.BidCheckService;
import com.hfusionhub.service.BidPlanGateService;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 废标风险自检服务实现（招投标垂直化 · P1）
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class BidCheckServiceImpl implements BidCheckService {

    private static final Set<String> VALID_REPORT_STATUSES =
            Set.of(BidCheckReport.STATUS_CONFIRMED, BidCheckReport.STATUS_FIXED);

    private static final Map<String, Integer> SEVERITY_ORDER = Map.of(
            BidCheckReport.SEVERITY_CRITICAL, 0,
            BidCheckReport.SEVERITY_WARNING, 1,
            BidCheckReport.SEVERITY_INFO, 2);

    private final BidProjectMapper bidProjectMapper;
    private final BidRequirementMapper bidRequirementMapper;
    private final BidDraftMapper bidDraftMapper;
    private final BidCheckReportMapper bidCheckReportMapper;
    private final JwtUtils jwtUtils;
    private final AiClient aiClient;
    private final UsageLedgerService usageLedgerService;
    private final ObjectMapper objectMapper;
    private final BidPlanGateService bidPlanGateService;

    @Override
    @Transactional
    public Map<String, Object> check(Long projectId) {
        BidProject project = requireOwnedProject(projectId);
        bidPlanGateService.requireModule(
                TenantContext.requireTenantId(), BidSubscription.MODULE_CHECK, "废标自检");

        List<BidDraft> drafts = bidDraftMapper.selectList(new LambdaQueryWrapper<BidDraft>()
                .eq(BidDraft::getProjectId, projectId));
        List<Map<String, Object>> sectionMaps = new ArrayList<>();
        for (BidDraft draft : drafts) {
            Map<String, Object> map = new HashMap<>();
            map.put("section_key", draft.getSectionKey());
            map.put("section_title", draft.getSectionTitle());
            map.put("content", draft.getContent());
            sectionMaps.add(map);
        }
        List<BidRequirement> requirements = bidRequirementMapper.selectList(
                new LambdaQueryWrapper<BidRequirement>()
                        .eq(BidRequirement::getProjectId, projectId)
                        .orderByAsc(BidRequirement::getId));
        List<Map<String, Object>> reqMaps = new ArrayList<>();
        for (BidRequirement req : requirements) {
            Map<String, Object> map = new HashMap<>();
            map.put("category", req.getCategory());
            map.put("requirement", req.getRequirement());
            map.put("source_clause", req.getSourceClause());
            reqMaps.add(map);
        }

        Map<String, Object> result = aiClient.bidCheck(
                projectId, project.getTitle(), project.getTenderNumber(),
                List.of(project.getKnowledgeBaseId()), sectionMaps, reqMaps);
        if (!"ok".equals(result.get("status"))) {
            throw new BusinessException(
                    StatusCode.SERVICE_UNAVAILABLE,
                    result.get("message") != null ? String.valueOf(result.get("message")) : "自检失败，请稍后重试");
        }

        // 幂等落库：清空旧报告后写入本次结果
        bidCheckReportMapper.delete(new LambdaQueryWrapper<BidCheckReport>()
                .eq(BidCheckReport::getProjectId, projectId));
        List<BidCheckReport> reports = persistFindings(projectId, result.get("findings"));
        if (!reports.isEmpty()) {
            // 计量：自检报告份数（P1-7），按报告条数计
            String key = "bid-check:" + projectId;
            usageLedgerService.reserve(UsageMeter.BID_CHECK_REPORTS, key, reports.size(), "bid_project",
                    String.valueOf(projectId));
            usageLedgerService.settle(UsageMeter.BID_CHECK_REPORTS, key, reports.size(), "bid_project",
                    String.valueOf(projectId));
        }

        project.setStatus(BidProject.STATUS_CHECKING);
        bidProjectMapper.updateById(project);
        log.info("废标自检完成，projectId: {}, findings: {}", projectId, reports.size());

        Object rawSummary = result.get("summary");
        Map<String, Object> summary = new HashMap<>();
        if (rawSummary instanceof Map) {
            summary.putAll((Map<String, Object>) rawSummary);
        }
        summary.put("total", reports.size());
        return summary;
    }

    @Override
    public List<BidCheckReport> listReports(Long projectId) {
        requireOwnedProject(projectId);
        List<BidCheckReport> reports = bidCheckReportMapper.selectList(
                new LambdaQueryWrapper<BidCheckReport>()
                        .eq(BidCheckReport::getProjectId, projectId));
        reports.sort((a, b) -> Integer.compare(
                SEVERITY_ORDER.getOrDefault(b.getSeverity(), 3),
                SEVERITY_ORDER.getOrDefault(a.getSeverity(), 3)));
        return reports;
    }

    @Override
    @Transactional
    public void updateReportStatus(Long reportId, String status) {
        if (!VALID_REPORT_STATUSES.contains(status)) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "非法的报告状态：" + status);
        }
        BidCheckReport report = bidCheckReportMapper.selectById(reportId);
        if (report == null) {
            throw new BusinessException(StatusCode.NOT_FOUND, "自检报告不存在");
        }
        requireOwnedProject(report.getProjectId());
        report.setStatus(status);
        bidCheckReportMapper.updateById(report);
        log.info("自检报告状态更新，reportId: {}, status: {}", reportId, status);
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
    private List<BidCheckReport> persistFindings(Long projectId, Object raw) {
        List<BidCheckReport> reports = new ArrayList<>();
        if (!(raw instanceof List)) {
            return reports;
        }
        for (Object item : (List<Object>) raw) {
            if (!(item instanceof Map)) {
                continue;
            }
            Map<String, Object> m = (Map<String, Object>) item;
            BidCheckReport report = new BidCheckReport();
            report.setProjectId(projectId);
            report.setSectionKey(asStringOrNull(m.get("section_key")));
            report.setSeverity(asStringOrDefault(m.get("severity"), BidCheckReport.SEVERITY_WARNING));
            report.setCategory(asStringOrDefault(m.get("category"), BidCheckReport.CATEGORY_DISQUALIFICATION));
            report.setFinding(asStringOrNull(m.get("finding")));
            report.setEvidence(jsonOrNull(m.get("evidence_chunk_ids")));
            report.setSuggestedFix(asStringOrNull(m.get("suggested_fix")));
            report.setStatus(BidCheckReport.STATUS_OPEN);
            if (report.getFinding() == null) {
                continue;
            }
            bidCheckReportMapper.insert(report);
            reports.add(report);
        }
        return reports;
    }

    private String asStringOrNull(Object value) {
        if (value == null) {
            return null;
        }
        String s = String.valueOf(value);
        return s.isBlank() ? null : s;
    }

    private String asStringOrDefault(Object value, String defaultValue) {
        String s = asStringOrNull(value);
        return s == null ? defaultValue : s;
    }

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
            return String.valueOf(value);
        }
    }
}
