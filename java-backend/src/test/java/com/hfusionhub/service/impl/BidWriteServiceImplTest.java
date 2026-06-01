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
import com.hfusionhub.entity.BidDraft;
import com.hfusionhub.entity.BidProject;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.BidDraftMapper;
import com.hfusionhub.mapper.BidProjectMapper;
import com.hfusionhub.mapper.BidRequirementMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
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
 * 标书撰写服务单元测试（招投标垂直化 · P1）
 *
 * @author HFusionHub Team
 */
@ExtendWith(MockitoExtension.class)
class BidWriteServiceImplTest {

    @Mock private BidProjectMapper bidProjectMapper;
    @Mock private BidRequirementMapper bidRequirementMapper;
    @Mock private BidDraftMapper bidDraftMapper;
    @Mock private KnowledgeBaseMapper knowledgeBaseMapper;
    @Mock private JwtUtils jwtUtils;
    @Mock private AiClient aiClient;
    @Mock private UsageLedgerService usageLedgerService;
    @Mock private BidPlanGateService bidPlanGateService;

    private BidWriteServiceImpl service;
    private MockedStatic<JwtUtils> jwtUtilsMock;

    @BeforeEach
    void setUp() {
        service = new BidWriteServiceImpl(
                bidProjectMapper,
                bidRequirementMapper,
                bidDraftMapper,
                knowledgeBaseMapper,
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
        p.setStatus(BidProject.STATUS_REQUIREMENTS);
        return p;
    }

    @Test
    void writeRejectsProjectNotOwned() {
        when(bidProjectMapper.selectById(1L)).thenReturn(project(1L, 99L));
        assertThrows(BusinessException.class, () -> service.write(1L));
        verify(bidDraftMapper, never()).insert(any());
    }

    @Test
    void writeBlockedWhenDraftModuleNotGranted() {
        when(bidProjectMapper.selectById(1L)).thenReturn(project(1L, 7L));
        org.mockito.Mockito.doThrow(new BusinessException(
                        com.hfusionhub.common.constant.StatusCode.FORBIDDEN, "标书撰写需要开通「标书撰写」模块"))
                .when(bidPlanGateService).requireModule(anyLong(), any(), any());

        assertThrows(BusinessException.class, () -> service.write(1L));
        // 模块未开通时不调用 Python 撰写，也不落库
        verify(aiClient, never()).bidWrite(anyLong(), any(), any(), any(), any(), any());
        verify(bidDraftMapper, never()).insert(any());
    }

    @Test
    void writePersistsSectionsAndMetersChars() {
        when(bidProjectMapper.selectById(1L)).thenReturn(project(1L, 7L));
        when(bidRequirementMapper.selectList(any())).thenReturn(List.of());
        when(aiClient.bidWrite(anyLong(), any(), any(), any(), any(), any())).thenReturn(Map.of(
                "status", "ok",
                "sections", List.of(
                        Map.of(
                                "section_key", "commercial",
                                "section_title", "商务标",
                                "content", "报价说明与商务承诺。",
                                "evidence_chunk_ids", List.of("c1")),
                        Map.of(
                                "section_key", "technical",
                                "section_title", "技术方案",
                                "content", "技术方案正文。",
                                "evidence_chunk_ids", List.of("c2")))));

        java.util.List<BidDraft> drafts = service.write(1L);

        assertEquals(2, drafts.size());
        ArgumentCaptor<BidDraft> captor = ArgumentCaptor.forClass(BidDraft.class);
        verify(bidDraftMapper, org.mockito.Mockito.times(2)).insert(captor.capture());
        BidDraft inserted = captor.getAllValues().stream()
                .filter(d -> "commercial".equals(d.getSectionKey()))
                .findFirst()
                .orElseThrow();
        assertEquals(Integer.valueOf(1), inserted.getVersion());
        assertEquals(BidDraft.STATUS_DRAFTING, inserted.getStatus());
        // 项目推进至 drafting
        ArgumentCaptor<BidProject> projectCaptor = ArgumentCaptor.forClass(BidProject.class);
        verify(bidProjectMapper).updateById(projectCaptor.capture());
        assertEquals(BidProject.STATUS_DRAFTING, projectCaptor.getValue().getStatus());
        // 计量：按产出字符数（10 字 + 7 字 = 17）
        verify(usageLedgerService).reserve(eq(UsageMeter.BID_DRAFT_CHARS), any(), eq(17L),
                eq("bid_project"), any());
        verify(usageLedgerService).settle(eq(UsageMeter.BID_DRAFT_CHARS), any(), eq(17L),
                eq("bid_project"), any());
    }

    @Test
    void writeIncludesQualificationAndHistoryKbs() {
        // P1-6：撰写自动并入项目创建者的资质库 + 历史标书库，演示"历史标书复用撰写"
        when(bidProjectMapper.selectById(1L)).thenReturn(project(1L, 7L));
        when(bidRequirementMapper.selectList(any())).thenReturn(List.of());
        KnowledgeBase qualKb = new KnowledgeBase();
        qualKb.setId(51L);
        qualKb.setCategory(KnowledgeBase.CATEGORY_QUALIFICATION);
        qualKb.setUserId(7L);
        qualKb.setStatus(KnowledgeBase.STATUS_NORMAL);
        KnowledgeBase histKb = new KnowledgeBase();
        histKb.setId(52L);
        histKb.setCategory(KnowledgeBase.CATEGORY_BID_HISTORY);
        histKb.setUserId(7L);
        histKb.setStatus(KnowledgeBase.STATUS_NORMAL);
        when(knowledgeBaseMapper.selectList(any())).thenReturn(List.of(qualKb, histKb));
        when(aiClient.bidWrite(anyLong(), any(), any(), any(), any(), any())).thenReturn(Map.of(
                "status", "ok",
                "sections", List.of(
                        Map.of("section_key", "commercial", "section_title", "商务标",
                                "content", "报价说明与商务承诺。", "evidence_chunk_ids", List.of("c1")))));

        service.write(1L);

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<Long>> kbCaptor = ArgumentCaptor.forClass(List.class);
        verify(aiClient).bidWrite(anyLong(), any(), any(), kbCaptor.capture(), any(), any());
        assertEquals(List.of(5L, 51L, 52L), kbCaptor.getValue());
    }

    @Test
    void writePropagatesAiFailure() {
        when(bidProjectMapper.selectById(1L)).thenReturn(project(1L, 7L));
        when(bidRequirementMapper.selectList(any())).thenReturn(List.of());
        when(aiClient.bidWrite(anyLong(), any(), any(), any(), any(), any()))
                .thenReturn(Map.of("status", "error", "message", "撰写服务不可用"));

        assertThrows(BusinessException.class, () -> service.write(1L));
        verify(bidDraftMapper, never()).insert(any());
    }

    @Test
    void updateDraftStatusApprovesAndRecordsApprover() {
        BidDraft draft = new BidDraft();
        draft.setId(10L);
        draft.setProjectId(1L);
        draft.setStatus(BidDraft.STATUS_DRAFTING);
        when(bidDraftMapper.selectById(10L)).thenReturn(draft);
        when(bidProjectMapper.selectById(1L)).thenReturn(project(1L, 7L));

        service.updateDraftStatus(10L, BidDraft.STATUS_APPROVED);

        assertEquals(BidDraft.STATUS_APPROVED, draft.getStatus());
        assertEquals(Long.valueOf(7L), draft.getApprovedBy());
        verify(bidDraftMapper).updateById(draft);
    }

    @Test
    void updateDraftStatusRejectsInvalidStatus() {
        assertThrows(BusinessException.class, () -> service.updateDraftStatus(10L, "nonsense"));
    }
}
