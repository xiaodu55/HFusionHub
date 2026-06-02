package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.BidCheckReport;
import com.hfusionhub.entity.BidDraft;
import com.hfusionhub.entity.BidProject;
import com.hfusionhub.mapper.BidCheckReportMapper;
import com.hfusionhub.mapper.BidDraftMapper;
import com.hfusionhub.mapper.BidProjectMapper;
import com.hfusionhub.mapper.BidRequirementMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.BidPlanGateService;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 废标风险自检服务单元测试（招投标垂直化 · P1）
 *
 * @author HFusionHub Team
 */
@ExtendWith(MockitoExtension.class)
class BidCheckServiceImplTest {

    @Mock private BidProjectMapper bidProjectMapper;
    @Mock private BidRequirementMapper bidRequirementMapper;
    @Mock private BidDraftMapper bidDraftMapper;
    @Mock private BidCheckReportMapper bidCheckReportMapper;
    @Mock private JwtUtils jwtUtils;
    @Mock private AiClient aiClient;
    @Mock private UsageLedgerService usageLedgerService;
    @Mock private BidPlanGateService bidPlanGateService;

    private BidCheckServiceImpl service;
    private MockedStatic<JwtUtils> jwtUtilsMock;

    @BeforeEach
    void setUp() {
        service = new BidCheckServiceImpl(
                bidProjectMapper,
                bidRequirementMapper,
                bidDraftMapper,
                bidCheckReportMapper,
                jwtUtils,
                aiClient,
                usageLedgerService,
                new ObjectMapper(),
                bidPlanGateService);
        jwtUtilsMock = org.mockito.Mockito.mockStatic(JwtUtils.class);
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(7L);
        TenantContext.setTenantId(7L);
    }

    @AfterEach
    void tearDown() {
        jwtUtilsMock.close();
        TenantContext.clear();
    }

    private BidProject project(Long id, Long userId) {
        BidProject p = new BidProject();
        p.setId(id);
        p.setKnowledgeBaseId(5L);
        p.setTitle("某园区智能化改造项目");
        p.setCreatedBy(userId);
        p.setStatus(BidProject.STATUS_DRAFTING);
        return p;
    }

    private BidDraft draft(String sectionKey) {
        BidDraft d = new BidDraft();
        d.setId(10L);
        d.setProjectId(1L);
        d.setSectionKey(sectionKey);
        d.setContent("技术方案正文");
        return d;
    }

    @Test
    void checkRejectsProjectNotOwned() {
        when(bidProjectMapper.selectById(1L)).thenReturn(project(1L, 99L));
        assertThrows(BusinessException.class, () -> service.check(1L));
        verify(bidCheckReportMapper, never()).insert(any());
    }

    @Test
    void checkBlockedWhenCheckModuleNotGranted() {
        when(bidProjectMapper.selectById(1L)).thenReturn(project(1L, 7L));
        org.mockito.Mockito.doThrow(new BusinessException(
                        com.hfusionhub.common.constant.StatusCode.FORBIDDEN, "废标自检需要开通「废标自检」模块"))
                .when(bidPlanGateService).requireModule(anyLong(), any(), any());

        assertThrows(BusinessException.class, () -> service.check(1L));
        // 模块未开通时不调用 Python 自检，也不落库
        verify(aiClient, never()).bidCheck(anyLong(), any(), any(), any(), any(), any());
        verify(bidCheckReportMapper, never()).insert(any());
    }

    @Test
    void checkForApiBlockedWhenOpenApiModuleNotGranted() {
        org.mockito.Mockito.doThrow(new BusinessException(
                        com.hfusionhub.common.constant.StatusCode.FORBIDDEN, "投标开放 API 需要开通「投标开放 API」模块"))
                .when(bidPlanGateService).requireModule(7L, "openapi", "投标开放 API");

        assertThrows(BusinessException.class, () -> service.checkForApi(1L, 7L));
        verify(aiClient, never()).bidCheck(anyLong(), any(), any(), any(), any(), any());
    }

    @Test
    void checkForApiRunsUnderTenantScope() {
        // openapi 路径按租户过滤项目（调用方置于 app 租户上下文），不校验 createdBy
        when(bidProjectMapper.selectById(1L)).thenReturn(project(1L, 99L));
        when(bidDraftMapper.selectList(any())).thenReturn(List.of());
        when(bidRequirementMapper.selectList(any())).thenReturn(List.of());
        when(aiClient.bidCheck(anyLong(), any(), any(), any(), any(), any())).thenReturn(Map.of(
                "status", "ok",
                "findings", List.of(),
                "summary", Map.of("total", 0, "critical", 0, "warning", 0, "info", 0)));

        Map<String, Object> summary = service.checkForApi(1L, 7L);

        assertEquals(0, summary.get("total"));
        verify(bidProjectMapper).updateById(any());
    }

    @Test
    void checkForApiRejectsProjectNotFound() {
        when(bidProjectMapper.selectById(99L)).thenReturn(null);
        assertThrows(BusinessException.class, () -> service.checkForApi(99L, 7L));
    }

    @Test
    void checkPersistsFindingsAndMetersReports() {
        when(bidProjectMapper.selectById(1L)).thenReturn(project(1L, 7L));
        when(bidDraftMapper.selectList(any())).thenReturn(List.of(draft("technical")));
        when(bidRequirementMapper.selectList(any())).thenReturn(List.of());
        when(aiClient.bidCheck(anyLong(), any(), any(), any(), any(), any())).thenReturn(Map.of(
                "status", "ok",
                "findings", List.of(
                        Map.of(
                                "severity", "critical",
                                "category", "bond",
                                "finding", "招标文件要求投标保证金 20万元，标书未体现",
                                "evidence_chunk_ids", List.of("c1"),
                                "suggested_fix", "在商务标补充保证金金额")),
                "summary", Map.of("total", 1, "critical", 1, "warning", 0, "info", 0)));

        Map<String, Object> summary = service.check(1L);

        assertEquals(1, summary.get("critical"));
        // 幂等：先清空旧报告
        verify(bidCheckReportMapper).delete(any());
        ArgumentCaptor<BidCheckReport> captor = ArgumentCaptor.forClass(BidCheckReport.class);
        verify(bidCheckReportMapper).insert(captor.capture());
        BidCheckReport inserted = captor.getValue();
        assertEquals(BidCheckReport.SEVERITY_CRITICAL, inserted.getSeverity());
        assertEquals(BidCheckReport.STATUS_OPEN, inserted.getStatus());
        // 项目推进至 checking
        ArgumentCaptor<BidProject> projectCaptor = ArgumentCaptor.forClass(BidProject.class);
        verify(bidProjectMapper).updateById(projectCaptor.capture());
        assertEquals(BidProject.STATUS_CHECKING, projectCaptor.getValue().getStatus());
        // 计量：自检报告份数
        verify(usageLedgerService).reserve(eq(UsageMeter.BID_CHECK_REPORTS), eq("bid-check:1"), eq(1L),
                eq("bid_project"), eq("1"));
        verify(usageLedgerService).settle(eq(UsageMeter.BID_CHECK_REPORTS), eq("bid-check:1"), eq(1L),
                eq("bid_project"), eq("1"));
    }

    @Test
    void checkPropagatesAiFailure() {
        when(bidProjectMapper.selectById(1L)).thenReturn(project(1L, 7L));
        when(bidDraftMapper.selectList(any())).thenReturn(List.of(draft("technical")));
        when(aiClient.bidCheck(anyLong(), any(), any(), any(), any(), any()))
                .thenReturn(Map.of("status", "error", "message", "自检服务不可用"));

        assertThrows(BusinessException.class, () -> service.check(1L));
        verify(bidCheckReportMapper, never()).insert(any());
    }

    @Test
    void updateReportStatusConfirms() {
        BidCheckReport report = new BidCheckReport();
        report.setId(20L);
        report.setProjectId(1L);
        report.setStatus(BidCheckReport.STATUS_OPEN);
        when(bidCheckReportMapper.selectById(20L)).thenReturn(report);
        when(bidProjectMapper.selectById(1L)).thenReturn(project(1L, 7L));

        service.updateReportStatus(20L, BidCheckReport.STATUS_CONFIRMED);

        assertEquals(BidCheckReport.STATUS_CONFIRMED, report.getStatus());
        verify(bidCheckReportMapper).updateById(report);
    }

    @Test
    void updateReportStatusRejectsInvalid() {
        assertThrows(BusinessException.class, () -> service.updateReportStatus(20L, "nonsense"));
    }
}
