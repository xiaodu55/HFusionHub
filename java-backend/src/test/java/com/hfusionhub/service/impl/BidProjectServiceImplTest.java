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
import com.hfusionhub.dto.BidProjectCreateDTO;
import com.hfusionhub.entity.BidProject;
import com.hfusionhub.entity.BidRequirement;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.BidProjectMapper;
import com.hfusionhub.mapper.BidRequirementMapper;
import com.hfusionhub.mapper.BidScoringMethodMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.TenderElementMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.UsageLedgerService;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 投标项目服务单元测试（招投标垂直化）
 *
 * @author HFusionHub Team
 */
@ExtendWith(MockitoExtension.class)
class BidProjectServiceImplTest {

    @Mock private BidProjectMapper bidProjectMapper;
    @Mock private TenderElementMapper tenderElementMapper;
    @Mock private BidScoringMethodMapper bidScoringMethodMapper;
    @Mock private BidRequirementMapper bidRequirementMapper;
    @Mock private KnowledgeBaseMapper knowledgeBaseMapper;
    @Mock private JwtUtils jwtUtils;
    @Mock private AiClient aiClient;
    @Mock private UsageLedgerService usageLedgerService;

    private BidProjectServiceImpl service;
    private MockedStatic<JwtUtils> jwtUtilsMock;

    @BeforeEach
    void setUp() {
        service = new BidProjectServiceImpl(
                bidProjectMapper,
                tenderElementMapper,
                bidScoringMethodMapper,
                bidRequirementMapper,
                knowledgeBaseMapper,
                jwtUtils,
                aiClient,
                new ObjectMapper(),
                usageLedgerService);
        jwtUtilsMock = org.mockito.Mockito.mockStatic(JwtUtils.class);
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(7L);
    }

    @AfterEach
    void tearDown() {
        jwtUtilsMock.close();
    }

    private KnowledgeBase kb(Long id, Long userId) {
        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(id);
        kb.setUserId(userId);
        kb.setName("招标文件库");
        kb.setCategory("tender");
        return kb;
    }

    private BidProject project(Long id, Long userId) {
        BidProject p = new BidProject();
        p.setId(id);
        p.setKnowledgeBaseId(5L);
        p.setTitle("某园区智能化改造项目");
        p.setCreatedBy(userId);
        p.setStatus(BidProject.STATUS_INTERPRETING);
        return p;
    }

    @Test
    void createRejectsKbNotOwnedByCurrentUser() {
        when(knowledgeBaseMapper.selectById(5L)).thenReturn(kb(5L, 99L));

        BidProjectCreateDTO dto = new BidProjectCreateDTO();
        dto.setKnowledgeBaseId(5L);
        dto.setTitle("项目A");

        assertThrows(BusinessException.class, () -> service.create(dto));
        verify(bidProjectMapper, never()).insert(any());
    }

    @Test
    void createSucceedsWhenKbOwned() {
        when(knowledgeBaseMapper.selectById(5L)).thenReturn(kb(5L, 7L));
        BidProjectCreateDTO dto = new BidProjectCreateDTO();
        dto.setKnowledgeBaseId(5L);
        dto.setTitle("项目A");
        dto.setBudget(new BigDecimal("1200000"));

        service.create(dto);

        verify(bidProjectMapper).insert(any(BidProject.class));
        // 商业化骨架：创建即计量 BID_PROJECTS
        verify(usageLedgerService).reserve(eq(UsageMeter.BID_PROJECTS), any(), eq(1L), eq("bid_project"), any());
        verify(usageLedgerService).settle(eq(UsageMeter.BID_PROJECTS), any(), eq(1L), eq("bid_project"), any());
    }

    @Test
    void getByIdRejectsProjectNotOwned() {
        when(bidProjectMapper.selectById(1L)).thenReturn(project(1L, 99L));
        assertThrows(BusinessException.class, () -> service.getById(1L));
    }

    @Test
    void updateStatusRejectsInvalidStatus() {
        assertThrows(BusinessException.class, () -> service.updateStatus(1L, "nonsense"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void interpretPersistsResultsAndMarksLowConfidenceAsManualReview() {
        BidProject p = project(1L, 7L);
        when(bidProjectMapper.selectById(1L)).thenReturn(p);

        Map<String, Object> result = Map.of(
                "status", "ok",
                "elements", List.of(
                        Map.of(
                                "element_key", "budget",
                                "element_value", "1200000",
                                "confidence", 0.95,
                                "source_clause", "预算不超过120万元",
                                "evidence_chunk_ids", List.of("c1"))),
                "scoring_methods", List.of(
                        Map.of("method_type", "comprehensive", "total_score", 100, "points_json",
                                "[{\"name\":\"技术分\",\"max_score\":50}]")),
                "requirements", List.of(
                        Map.of(
                                "category", BidRequirement.CATEGORY_QUALIFICATION,
                                "requirement", "须具备建筑智能化二级以上资质",
                                "source_clause", "资质要求",
                                "confidence", 0.4), // 低置信 → manual_review
                        Map.of(
                                "category", BidRequirement.CATEGORY_PERFORMANCE,
                                "requirement", "近三年同类业绩不少于2项",
                                "confidence", 0.9))); // 高置信 → pending
        when(aiClient.bidInterpret(anyLong(), anyLong(), any(), any())).thenReturn(result);

        service.interpret(1L);

        verify(tenderElementMapper).insert(any());
        verify(bidScoringMethodMapper).insert(any());
        // 捕获插入的需求，验证低置信兜底
        org.mockito.ArgumentCaptor<BidRequirement> captor =
                org.mockito.ArgumentCaptor.forClass(BidRequirement.class);
        verify(bidRequirementMapper, org.mockito.Mockito.times(2)).insert(captor.capture());
        java.util.List<BidRequirement> inserted = captor.getAllValues();
        assertEquals(2, inserted.size());
        boolean hasManualReview = inserted.stream()
                .anyMatch(r -> BidRequirement.STATUS_MANUAL_REVIEW.equals(r.getSatisfiedStatus()));
        boolean hasPending = inserted.stream()
                .anyMatch(r -> BidRequirement.STATUS_PENDING.equals(r.getSatisfiedStatus()));
        assertEquals(true, hasManualReview);
        assertEquals(true, hasPending);
        assertEquals(BidProject.STATUS_REQUIREMENTS, p.getStatus());
        // 商业化骨架：解读即按 要素 + 需求 总数计量 TENDER_ELEMENTS（1 要素 + 2 需求 = 3）
        verify(usageLedgerService).reserve(eq(UsageMeter.TENDER_ELEMENTS), eq("bid-interpret:1"), eq(3L),
                eq("bid_project"), eq("1"));
        verify(usageLedgerService).settle(eq(UsageMeter.TENDER_ELEMENTS), eq("bid-interpret:1"), eq(3L),
                eq("bid_project"), eq("1"));
    }

    @Test
    void interpretPropagatesAiServiceFailure() {
        when(bidProjectMapper.selectById(1L)).thenReturn(project(1L, 7L));
        when(aiClient.bidInterpret(anyLong(), anyLong(), any(), any()))
                .thenReturn(Map.of("status", "error", "message", "解读服务不可用"));

        assertThrows(BusinessException.class, () -> service.interpret(1L));
        verify(tenderElementMapper, never()).insert(any());
    }
}
