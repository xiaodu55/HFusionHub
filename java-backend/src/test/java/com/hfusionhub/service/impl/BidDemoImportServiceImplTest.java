package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.dev33.satoken.SaManager;
import cn.dev33.satoken.context.SaTokenContext;
import cn.dev33.satoken.context.model.SaRequest;
import cn.dev33.satoken.context.model.SaResponse;
import cn.dev33.satoken.context.model.SaStorage;
import cn.dev33.satoken.dao.SaTokenDaoDefaultImpl;
import cn.dev33.satoken.stp.StpUtil;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.dto.DemoImportResultDTO;
import com.hfusionhub.entity.BidProject;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.BidProjectMapper;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.service.KnowledgeBaseService;
import com.hfusionhub.service.VectorizationService;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * Unit tests for {@link BidDemoImportServiceImpl} - 招投标演示数据导入。
 *
 * <p>Verifies: tender KB creation/reuse (category=tender), per-document
 * idempotent import, file persistence, parse trigger, graceful handling when
 * the AI service is unreachable, and the demo bid project seeding/clearing.</p>
 */
class BidDemoImportServiceImplTest {

    @TempDir
    Path tempDir;

    private KnowledgeBaseMapper knowledgeBaseMapper;
    private DocumentMapper documentMapper;
    private BidProjectMapper bidProjectMapper;
    private VectorizationService vectorizationService;
    private KnowledgeBaseService knowledgeBaseService;
    private BidDemoImportServiceImpl service;

    @BeforeEach
    void setUp() {
        // Install in-memory Sa-Token DAO + mock web context so StpUtil works
        SaManager.setSaTokenDao(new SaTokenDaoDefaultImpl());
        SaManager.setSaTokenContext(new MockSaTokenContext());

        knowledgeBaseMapper = mock(KnowledgeBaseMapper.class);
        documentMapper = mock(DocumentMapper.class);
        bidProjectMapper = mock(BidProjectMapper.class);
        vectorizationService = mock(VectorizationService.class);
        knowledgeBaseService = mock(KnowledgeBaseService.class);
        service = new BidDemoImportServiceImpl(
                knowledgeBaseMapper,
                documentMapper,
                bidProjectMapper,
                vectorizationService,
                knowledgeBaseService);
        // 演示文档写入临时目录，避免污染工作区
        ReflectionTestUtils.setField(service, "uploadDir", tempDir.toString());
        StpUtil.login(1L);
    }

    @AfterEach
    void tearDown() {
        StpUtil.logout();
    }

    private DemoImportResultDTO.SectionResult sectionOf(DemoImportResultDTO result, String section) {
        return result.getSections().stream()
                .filter(s -> section.equals(s.getSection()))
                .findFirst()
                .orElseThrow(() -> new AssertionError("缺少分项: " + section));
    }

    @Test
    void freshImportCreatesTenderKbWritesFilesAndSeedsProject() throws Exception {
        when(knowledgeBaseMapper.selectOne(any())).thenReturn(null);
        when(knowledgeBaseMapper.insert(any(KnowledgeBase.class))).thenAnswer(inv -> {
            KnowledgeBase kb = inv.getArgument(0);
            kb.setId(201L);
            return 1;
        });
        when(documentMapper.selectCount(any())).thenReturn(0L);
        when(bidProjectMapper.selectCount(any())).thenReturn(0L);
        AtomicLong idSeq = new AtomicLong(10);
        when(documentMapper.insert(any(Document.class))).thenAnswer(inv -> {
            Document doc = inv.getArgument(0);
            doc.setId(idSeq.getAndIncrement());
            return 1;
        });

        DemoImportResultDTO result = service.importBidDemoData();

        // P1-6：三类知识库共 7 篇文档（招标文件 4 + 资质库 1 + 历史标书 2）
        assertEquals(7, result.getImportedCount(), "应导入 7 篇演示文档");
        assertEquals(0, result.getSkippedCount());
        assertEquals(0, result.getParseFailedCount());
        assertEquals(201L, result.getKnowledgeBaseId());
        assertEquals("招投标演示知识库", result.getKnowledgeBaseName());
        // 知识库分类应为 tender（供投标项目解读工作流识别）
        org.mockito.ArgumentCaptor<KnowledgeBase> kbCaptor =
                org.mockito.ArgumentCaptor.forClass(KnowledgeBase.class);
        verify(knowledgeBaseMapper, times(3)).insert(kbCaptor.capture());
        assertEquals("tender", kbCaptor.getAllValues().get(0).getCategory());
        assertEquals("qualification", kbCaptor.getAllValues().get(1).getCategory());
        assertEquals("bid_history", kbCaptor.getAllValues().get(2).getCategory());
        verify(vectorizationService, times(7)).startVectorization(anyLong(), isNull());
        // 示例文档文件已写入上传目录
        long fileCount;
        try (var stream = Files.list(tempDir)) {
            fileCount = stream.count();
        }
        assertEquals(7, fileCount, "应写入 7 个演示文档文件");
        // 示例投标项目已创建
        verify(bidProjectMapper, times(1)).insert(any(BidProject.class));
        assertEquals(1, sectionOf(result, "bid_project").getImportedCount());
        assertEquals(4, sectionOf(result, "bid_kb").getImportedCount());
        assertEquals(1, sectionOf(result, "bid_qualification").getImportedCount());
        assertEquals(2, sectionOf(result, "bid_history").getImportedCount());
        assertTrue(result.getMessage().contains("解读"), "提示信息应引导到投标项目解读");
    }

    @Test
    void secondImportIsIdempotentAndSkipsExistingData() {
        KnowledgeBase existing = new KnowledgeBase();
        existing.setId(5L);
        existing.setName("招投标演示知识库");
        existing.setCategory("tender");
        when(knowledgeBaseMapper.selectOne(any())).thenReturn(existing);
        when(documentMapper.selectCount(any())).thenReturn(1L);
        when(bidProjectMapper.selectCount(any())).thenReturn(1L);

        DemoImportResultDTO result = service.importBidDemoData();

        assertEquals(0, result.getImportedCount());
        assertEquals(7, result.getSkippedCount());
        verify(knowledgeBaseMapper, never()).insert(any(KnowledgeBase.class));
        verify(documentMapper, never()).insert(any(Document.class));
        verify(vectorizationService, never()).startVectorization(anyLong(), any());
        verify(bidProjectMapper, never()).insert(any(BidProject.class));
        assertEquals(0, sectionOf(result, "bid_project").getImportedCount());
        assertEquals(1, sectionOf(result, "bid_project").getSkippedCount());
        assertEquals(4, sectionOf(result, "bid_kb").getSkippedCount());
    }

    @Test
    void parseFailureIsCountedAndDoesNotAbortImport() {
        when(knowledgeBaseMapper.selectOne(any())).thenReturn(null);
        when(knowledgeBaseMapper.insert(any(KnowledgeBase.class))).thenAnswer(inv -> {
            KnowledgeBase kb = inv.getArgument(0);
            kb.setId(7L);
            return 1;
        });
        when(documentMapper.selectCount(any())).thenReturn(0L);
        when(bidProjectMapper.selectCount(any())).thenReturn(0L);
        AtomicLong idSeq = new AtomicLong(10);
        when(documentMapper.insert(any(Document.class))).thenAnswer(inv -> {
            Document doc = inv.getArgument(0);
            doc.setId(idSeq.getAndIncrement());
            return 1;
        });
        doThrow(new BusinessException("AI 服务不可用")).when(vectorizationService).startVectorization(anyLong(), any());

        DemoImportResultDTO result = service.importBidDemoData();

        assertEquals(7, result.getImportedCount(), "文档仍应导入成功");
        assertEquals(7, result.getParseFailedCount(), "解析失败应被计数而非中断导入");
        assertTrue(result.getMessage().contains("重试"), "提示信息应包含重试指引");
        // 示例投标项目不受解析失败影响
        assertEquals(1, sectionOf(result, "bid_project").getImportedCount());
    }

    @Test
    void clearBidDemoDataRemovesProjectAndKb() {
        BidProject project = new BidProject();
        project.setId(30L);
        when(bidProjectMapper.selectList(any())).thenReturn(java.util.List.of(project));
        KnowledgeBase existing = new KnowledgeBase();
        existing.setId(5L);
        existing.setName("招投标演示知识库");
        when(knowledgeBaseMapper.selectOne(any())).thenReturn(existing);

        DemoImportResultDTO result = service.clearBidDemoData();

        verify(bidProjectMapper, times(1)).deleteById(30L);
        // P1-6：三个演示知识库（招标/资质/历史标书）全部移入回收站
        verify(knowledgeBaseService, times(3)).delete(5L);
        assertEquals(1, sectionOf(result, "bid_project").getImportedCount());
        assertEquals(1, sectionOf(result, "bid_kb_0").getImportedCount());
        assertEquals(1, sectionOf(result, "bid_kb_1").getImportedCount());
        assertEquals(1, sectionOf(result, "bid_kb_2").getImportedCount());
        assertTrue(result.getMessage().contains("已清除"), "提示信息应包含清除说明");
    }

    @Test
    void clearBidDemoDataIsNoopWhenNothingImported() {
        when(bidProjectMapper.selectList(any())).thenReturn(java.util.List.of());
        when(knowledgeBaseMapper.selectOne(any())).thenReturn(null);

        DemoImportResultDTO result = service.clearBidDemoData();

        verify(bidProjectMapper, never()).deleteById(anyLong());
        verify(knowledgeBaseService, never()).delete(anyLong());
        assertTrue(result.getMessage().contains("未发现"), "未导入时应提示无需清除");
    }

    /** Minimal in-memory SaTokenContext for unit tests without a servlet container. */
    private static class MockSaTokenContext implements SaTokenContext {
        private final Map<String, Object> storage = new HashMap<>();

        @Override
        public SaRequest getRequest() {
            return mock(SaRequest.class);
        }

        @Override
        public SaResponse getResponse() {
            return mock(SaResponse.class);
        }

        @Override
        public SaStorage getStorage() {
            return new SaStorage() {
                @Override
                public Object getSource() {
                    return storage;
                }

                @Override
                public Object get(String key) {
                    return storage.get(key);
                }

                @Override
                public SaStorage set(String key, Object value) {
                    storage.put(key, value);
                    return this;
                }

                @Override
                public SaStorage delete(String key) {
                    storage.remove(key);
                    return this;
                }
            };
        }

        @Override
        public boolean matchPath(String pattern, String path) {
            return true;
        }

        @Override
        public boolean isValid() {
            return true;
        }
    }
}
