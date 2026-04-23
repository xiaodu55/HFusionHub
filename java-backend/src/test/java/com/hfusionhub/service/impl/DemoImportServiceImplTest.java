package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.*;

import cn.dev33.satoken.SaManager;
import cn.dev33.satoken.context.SaTokenContext;
import cn.dev33.satoken.context.model.SaRequest;
import cn.dev33.satoken.context.model.SaResponse;
import cn.dev33.satoken.context.model.SaStorage;
import cn.dev33.satoken.dao.SaTokenDaoDefaultImpl;
import cn.dev33.satoken.stp.StpUtil;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.dto.DemoImportResultDTO;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
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
 * Unit tests for {@link DemoImportServiceImpl} — demo knowledge base import.
 *
 * <p>Verifies: KB creation/reuse, per-document idempotent import, file
 * persistence, parse trigger, and graceful handling when the AI service is
 * unreachable.</p>
 */
class DemoImportServiceImplTest {

    @TempDir
    Path tempDir;

    private KnowledgeBaseMapper knowledgeBaseMapper;
    private DocumentMapper documentMapper;
    private VectorizationService vectorizationService;
    private DemoImportServiceImpl service;

    @BeforeEach
    void setUp() {
        // Install in-memory Sa-Token DAO + mock web context so StpUtil works
        SaManager.setSaTokenDao(new SaTokenDaoDefaultImpl());
        SaManager.setSaTokenContext(new MockSaTokenContext());

        knowledgeBaseMapper = mock(KnowledgeBaseMapper.class);
        documentMapper = mock(DocumentMapper.class);
        vectorizationService = mock(VectorizationService.class);
        service = new DemoImportServiceImpl(knowledgeBaseMapper, documentMapper, vectorizationService);
        // 演示文档写入临时目录，避免污染工作区
        ReflectionTestUtils.setField(service, "uploadDir", tempDir.toString());
        StpUtil.login(1L);
    }

    @AfterEach
    void tearDown() {
        StpUtil.logout();
    }

    @Test
    void freshImportCreatesKbWritesFilesAndTriggersParse() throws Exception {
        when(knowledgeBaseMapper.selectOne(any())).thenReturn(null);
        when(knowledgeBaseMapper.insert(any(KnowledgeBase.class))).thenAnswer(inv -> {
            KnowledgeBase kb = inv.getArgument(0);
            kb.setId(100L);
            return 1;
        });
        when(documentMapper.selectCount(any())).thenReturn(0L);
        AtomicLong idSeq = new AtomicLong(10);
        when(documentMapper.insert(any(Document.class))).thenAnswer(inv -> {
            Document doc = inv.getArgument(0);
            doc.setId(idSeq.getAndIncrement());
            return 1;
        });

        DemoImportResultDTO result = service.importDemoKnowledgeBase();

        assertEquals(3, result.getImportedCount(), "应导入 3 篇示例文档");
        assertEquals(0, result.getSkippedCount());
        assertEquals(0, result.getParseFailedCount());
        assertEquals(100L, result.getKnowledgeBaseId());
        assertEquals("演示知识库", result.getKnowledgeBaseName());
        verify(vectorizationService, times(3)).startVectorization(anyLong(), isNull());
        // 示例文档文件已写入上传目录
        long fileCount;
        try (var stream = Files.list(tempDir)) {
            fileCount = stream.count();
        }
        assertEquals(3, fileCount, "应写入 3 个演示文档文件");
    }

    @Test
    void secondImportIsIdempotentAndSkipsExistingDocs() {
        KnowledgeBase existing = new KnowledgeBase();
        existing.setId(5L);
        existing.setName("演示知识库");
        when(knowledgeBaseMapper.selectOne(any())).thenReturn(existing);
        when(documentMapper.selectCount(any())).thenReturn(1L);

        DemoImportResultDTO result = service.importDemoKnowledgeBase();

        assertEquals(0, result.getImportedCount());
        assertEquals(3, result.getSkippedCount());
        verify(knowledgeBaseMapper, never()).insert(any(KnowledgeBase.class));
        verify(documentMapper, never()).insert(any(Document.class));
        verify(vectorizationService, never()).startVectorization(anyLong(), any());
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
        AtomicLong idSeq = new AtomicLong(10);
        when(documentMapper.insert(any(Document.class))).thenAnswer(inv -> {
            Document doc = inv.getArgument(0);
            doc.setId(idSeq.getAndIncrement());
            return 1;
        });
        doThrow(new BusinessException("AI 服务不可用")).when(vectorizationService).startVectorization(anyLong(), any());

        DemoImportResultDTO result = service.importDemoKnowledgeBase();

        assertEquals(3, result.getImportedCount(), "文档仍应导入成功");
        assertEquals(3, result.getParseFailedCount(), "解析失败应被计数而非中断导入");
        assertTrue(result.getMessage().contains("重试"), "提示信息应包含重试指引");
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
