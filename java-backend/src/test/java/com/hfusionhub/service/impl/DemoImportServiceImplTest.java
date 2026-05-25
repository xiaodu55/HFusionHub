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
import com.hfusionhub.entity.App;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.MemoryEntry;
import com.hfusionhub.entity.Note;
import com.hfusionhub.entity.PromptTemplate;
import com.hfusionhub.entity.SystemNotice;
import com.hfusionhub.mapper.AppMapper;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.MemoryEntryMapper;
import com.hfusionhub.mapper.NoteMapper;
import com.hfusionhub.mapper.PromptTemplateMapper;
import com.hfusionhub.mapper.SystemNoticeMapper;
import com.hfusionhub.service.KnowledgeBaseService;
import com.hfusionhub.service.PromptTemplateService;
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
 * Unit tests for {@link DemoImportServiceImpl} - demo data import.
 *
 * <p>Verifies: KB creation/reuse, per-document idempotent import, file
 * persistence, parse trigger, graceful handling when the AI service is
 * unreachable, and per-menu section seeding (prompts/notes/memory/app/notice).</p>
 */
class DemoImportServiceImplTest {

    @TempDir
    Path tempDir;

    private KnowledgeBaseMapper knowledgeBaseMapper;
    private DocumentMapper documentMapper;
    private VectorizationService vectorizationService;
    private PromptTemplateMapper promptTemplateMapper;
    private NoteMapper noteMapper;
    private MemoryEntryMapper memoryEntryMapper;
    private AppMapper appMapper;
    private SystemNoticeMapper systemNoticeMapper;
    private KnowledgeBaseService knowledgeBaseService;
    private PromptTemplateService promptTemplateService;
    private DemoImportServiceImpl service;

    @BeforeEach
    void setUp() {
        // Install in-memory Sa-Token DAO + mock web context so StpUtil works
        SaManager.setSaTokenDao(new SaTokenDaoDefaultImpl());
        SaManager.setSaTokenContext(new MockSaTokenContext());

        knowledgeBaseMapper = mock(KnowledgeBaseMapper.class);
        documentMapper = mock(DocumentMapper.class);
        vectorizationService = mock(VectorizationService.class);
        promptTemplateMapper = mock(PromptTemplateMapper.class);
        noteMapper = mock(NoteMapper.class);
        memoryEntryMapper = mock(MemoryEntryMapper.class);
        appMapper = mock(AppMapper.class);
        systemNoticeMapper = mock(SystemNoticeMapper.class);
        knowledgeBaseService = mock(KnowledgeBaseService.class);
        promptTemplateService = mock(PromptTemplateService.class);
        service = new DemoImportServiceImpl(
                knowledgeBaseMapper,
                documentMapper,
                vectorizationService,
                promptTemplateMapper,
                noteMapper,
                memoryEntryMapper,
                appMapper,
                systemNoticeMapper,
                knowledgeBaseService,
                promptTemplateService);
        // 演示文档写入临时目录，避免污染工作区
        ReflectionTestUtils.setField(service, "uploadDir", tempDir.toString());
        StpUtil.login(1L);
    }

    @AfterEach
    void tearDown() {
        StpUtil.logout();
    }

    /** 新菜单分项全部视为不存在（fresh import）。 */
    private void stubSectionsEmpty() {
        when(promptTemplateMapper.selectCount(any())).thenReturn(0L);
        when(noteMapper.selectCount(any())).thenReturn(0L);
        when(memoryEntryMapper.selectCount(any())).thenReturn(0L);
        when(appMapper.selectCount(any())).thenReturn(0L);
        when(systemNoticeMapper.selectCount(any())).thenReturn(0L);
    }

    /** 新菜单分项全部视为已存在（idempotent re-import）。 */
    private void stubSectionsFull() {
        when(promptTemplateMapper.selectCount(any())).thenReturn(1L);
        when(noteMapper.selectCount(any())).thenReturn(1L);
        when(memoryEntryMapper.selectCount(any())).thenReturn(1L);
        when(appMapper.selectCount(any())).thenReturn(1L);
        when(systemNoticeMapper.selectCount(any())).thenReturn(1L);
    }

    private DemoImportResultDTO.SectionResult sectionOf(DemoImportResultDTO result, String section) {
        return result.getSections().stream()
                .filter(s -> section.equals(s.getSection()))
                .findFirst()
                .orElseThrow(() -> new AssertionError("缺少分项: " + section));
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
        stubSectionsEmpty();
        AtomicLong idSeq = new AtomicLong(10);
        when(documentMapper.insert(any(Document.class))).thenAnswer(inv -> {
            Document doc = inv.getArgument(0);
            doc.setId(idSeq.getAndIncrement());
            return 1;
        });

        DemoImportResultDTO result = service.importDemoData();

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

        // 各菜单分项均应导入示例数据
        assertEquals(3, sectionOf(result, "kb").getImportedCount());
        assertEquals(3, sectionOf(result, "prompts").getImportedCount(), "应导入 3 个回答方案");
        assertEquals(2, sectionOf(result, "notes").getImportedCount(), "应导入 2 篇示例笔记");
        assertEquals(2, sectionOf(result, "memory").getImportedCount(), "应导入 2 条示例记忆");
        assertEquals(1, sectionOf(result, "apps").getImportedCount(), "应导入 1 个示例应用");
        assertEquals(1, sectionOf(result, "notices").getImportedCount(), "应导入 1 条欢迎公告");

        verify(promptTemplateMapper, times(3)).insert(any(PromptTemplate.class));
        verify(noteMapper, times(2)).insert(any(Note.class));
        verify(memoryEntryMapper, times(2)).insert(any(MemoryEntry.class));
        verify(appMapper, times(1)).insert(any(App.class));
        verify(systemNoticeMapper, times(1)).insert(any(SystemNotice.class));
    }

    @Test
    void secondImportIsIdempotentAndSkipsExistingData() {
        KnowledgeBase existing = new KnowledgeBase();
        existing.setId(5L);
        existing.setName("演示知识库");
        when(knowledgeBaseMapper.selectOne(any())).thenReturn(existing);
        when(documentMapper.selectCount(any())).thenReturn(1L);
        stubSectionsFull();

        DemoImportResultDTO result = service.importDemoData();

        assertEquals(0, result.getImportedCount());
        assertEquals(3, result.getSkippedCount());
        verify(knowledgeBaseMapper, never()).insert(any(KnowledgeBase.class));
        verify(documentMapper, never()).insert(any(Document.class));
        verify(vectorizationService, never()).startVectorization(anyLong(), any());
        // 各分项全部跳过
        result.getSections().forEach(s -> {
            assertEquals(0, s.getImportedCount(), s.getSection() + " 应跳过");
            assertTrue(s.getSkippedCount() > 0, s.getSection() + " 应有跳过计数");
        });
        verify(promptTemplateMapper, never()).insert(any(PromptTemplate.class));
        verify(noteMapper, never()).insert(any(Note.class));
        verify(memoryEntryMapper, never()).insert(any(MemoryEntry.class));
        verify(appMapper, never()).insert(any(App.class));
        verify(systemNoticeMapper, never()).insert(any(SystemNotice.class));
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
        stubSectionsEmpty();
        AtomicLong idSeq = new AtomicLong(10);
        when(documentMapper.insert(any(Document.class))).thenAnswer(inv -> {
            Document doc = inv.getArgument(0);
            doc.setId(idSeq.getAndIncrement());
            return 1;
        });
        doThrow(new BusinessException("AI 服务不可用")).when(vectorizationService).startVectorization(anyLong(), any());

        DemoImportResultDTO result = service.importDemoData();

        assertEquals(3, result.getImportedCount(), "文档仍应导入成功");
        assertEquals(3, result.getParseFailedCount(), "解析失败应被计数而非中断导入");
        assertTrue(result.getMessage().contains("重试"), "提示信息应包含重试指引");
        // 其他菜单分项不受解析失败影响
        assertEquals(3, sectionOf(result, "prompts").getImportedCount());
    }

    @Test
    void clearDemoDataRemovesAllSections() {
        KnowledgeBase existing = new KnowledgeBase();
        existing.setId(5L);
        existing.setName("演示知识库");
        when(knowledgeBaseMapper.selectOne(any())).thenReturn(existing);
        when(promptTemplateMapper.selectOne(any())).thenAnswer(inv -> {
            PromptTemplate t = new PromptTemplate();
            t.setId(10L);
            return t;
        });
        Note note = new Note();
        note.setId(20L);
        when(noteMapper.selectOne(any())).thenReturn(note);
        MemoryEntry memory = new MemoryEntry();
        memory.setId(30L);
        when(memoryEntryMapper.selectOne(any())).thenReturn(memory);
        App app = new App();
        app.setId(40L);
        when(appMapper.selectOne(any())).thenReturn(app);
        SystemNotice notice = new SystemNotice();
        notice.setId(50L);
        when(systemNoticeMapper.selectOne(any())).thenReturn(notice);

        DemoImportResultDTO result = service.clearDemoData();

        // 知识库与回答方案通过既有服务移入回收站
        verify(knowledgeBaseService, times(1)).delete(5L);
        verify(promptTemplateService, times(3)).delete(anyLong());
        // 其余菜单直接删除
        verify(noteMapper, times(2)).deleteById(anyLong());
        verify(memoryEntryMapper, times(2)).deleteById(anyLong());
        verify(appMapper, times(1)).deleteById(anyLong());
        verify(systemNoticeMapper, times(1)).deleteById(anyLong());
        assertTrue(result.getMessage().contains("已清除"), "提示信息应包含清除说明");
    }

    @Test
    void clearDemoDataIsNoopWhenNothingImported() {
        when(knowledgeBaseMapper.selectOne(any())).thenReturn(null);
        when(promptTemplateMapper.selectOne(any())).thenReturn(null);
        when(noteMapper.selectOne(any())).thenReturn(null);
        when(memoryEntryMapper.selectOne(any())).thenReturn(null);
        when(appMapper.selectOne(any())).thenReturn(null);
        when(systemNoticeMapper.selectOne(any())).thenReturn(null);

        DemoImportResultDTO result = service.clearDemoData();

        verify(knowledgeBaseService, never()).delete(anyLong());
        verify(promptTemplateService, never()).delete(anyLong());
        verify(noteMapper, never()).deleteById((java.io.Serializable) any());
        verify(memoryEntryMapper, never()).deleteById((java.io.Serializable) any());
        verify(appMapper, never()).deleteById((java.io.Serializable) any());
        verify(systemNoticeMapper, never()).deleteById((java.io.Serializable) any());
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
