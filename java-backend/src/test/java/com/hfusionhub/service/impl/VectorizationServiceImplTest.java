package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.ChunkDTO;
import com.hfusionhub.dto.DocumentChunkCallbackDTO;
import com.hfusionhub.dto.DocumentIndexCallbackDTO;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.DocumentChunk;
import com.hfusionhub.entity.DocumentIndexJob;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.User;
import com.hfusionhub.enums.DocumentStatus;
import com.hfusionhub.mapper.DocumentChunkMapper;
import com.hfusionhub.mapper.DocumentIndexJobMapper;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.RestTemplate;

@ExtendWith(MockitoExtension.class)
class VectorizationServiceImplTest {

    @Mock
    private DocumentMapper documentMapper;

    @Mock
    private KnowledgeBaseMapper knowledgeBaseMapper;

    @Mock
    private DocumentIndexJobMapper documentIndexJobMapper;

    @Mock
    private DocumentChunkMapper documentChunkMapper;

    @Mock
    private UserMapper userMapper;

    @Mock
    private UsageLedgerService usageLedgerService;

    @Mock
    private RestTemplate restTemplate;

    @Mock
    private PlatformTransactionManager transactionManager;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @InjectMocks
    private VectorizationServiceImpl vectorizationService;

    private MockedStatic<JwtUtils> jwtUtilsMock;

    @BeforeEach
    void setUp() {
        // 纯 Mockito 环境无 Spring 容器，需手动初始化 LambdaWrapper 的实体缓存
        com.baomidou.mybatisplus.core.metadata.TableInfoHelper.initTableInfo(
                new org.apache.ibatis.builder.MapperBuilderAssistant(
                        new com.baomidou.mybatisplus.core.MybatisConfiguration(), ""),
                com.hfusionhub.entity.DocumentIndexJob.class);
        // V77/S5: TransactionTemplate 直接持有 mock 的 PlatformTransactionManager，
        // getTransaction 返回 null / commit 为 no-op，回调会真实执行
        ReflectionTestUtils.setField(vectorizationService, "objectMapper", objectMapper);
        ReflectionTestUtils.setField(vectorizationService, "internalApiToken", "test-token");
        ReflectionTestUtils.setField(vectorizationService, "callbackSecret", "test-secret");
        ReflectionTestUtils.setField(vectorizationService, "pythonEngineUrl", "http://localhost:9000");
        ReflectionTestUtils.setField(vectorizationService, "bytesPerChunkEstimate", 300L);
        // Signed callbacks without X-Tenant-Id derive the tenant through
        // document -> knowledge base -> owner before processing the payload.
        // Keep that durable ownership available to callback-focused tests.
        org.mockito.Mockito.lenient().when(knowledgeBaseMapper.selectById(20L)).thenReturn(ownedKnowledgeBase());
        org.mockito.Mockito.lenient().when(userMapper.selectById(1L)).thenReturn(ownerUser(7L));
        jwtUtilsMock = org.mockito.Mockito.mockStatic(JwtUtils.class);
        jwtUtilsMock.when(JwtUtils::isLogin).thenReturn(true);
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);
    }

    @AfterEach
    void tearDown() {
        jwtUtilsMock.close();
        TenantContext.clear();
    }

    @Test
    void resetRejectsMissingDocument() {
        when(documentMapper.selectById(10L)).thenReturn(null);

        assertThrows(BusinessException.class, () -> vectorizationService.resetDocument(10L));
    }

    @Test
    void resetRejectsCompletedDocument() {
        Document document = ownedDocument(DocumentStatus.COMPLETED);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(ownedKnowledgeBase());

        assertThrows(BusinessException.class, () -> vectorizationService.resetDocument(10L));
        verify(documentMapper, never()).updateById(document);
    }

    @Test
    void resetMovesFailedDocumentToPending() {
        Document document = ownedDocument(DocumentStatus.FAILED);
        document.setErrorMessage("embedding failed");
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(ownedKnowledgeBase());

        vectorizationService.resetDocument(10L);

        assertEquals(DocumentStatus.PENDING.getCode(), document.getStatus());
        assertEquals(null, document.getErrorMessage());
        verify(documentMapper).updateById(document);
    }

    @Test
    void syncRejectsDocumentWithoutDurableJob() {
        Document document = ownedDocument(DocumentStatus.PROCESSING);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(ownedKnowledgeBase());
        when(documentIndexJobMapper.selectLatestByDocumentId(10L)).thenReturn(null);

        assertThrows(BusinessException.class, () -> vectorizationService.syncDocumentStatus(10L));
    }

    @Test
    void syncReturnsCompletedDocumentToPendingWhenChunksAreMissing() {
        Document document = ownedDocument(DocumentStatus.PROCESSING);
        DocumentIndexJob job = job("version-1", "COMPLETED", 3);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(ownedKnowledgeBase());
        when(documentIndexJobMapper.selectLatestByDocumentId(10L)).thenReturn(job);
        when(documentChunkMapper.countByDocumentId(10L, null)).thenReturn(0L);

        vectorizationService.syncDocumentStatus(10L);

        assertEquals(DocumentStatus.PENDING.getCode(), document.getStatus());
        assertEquals(0, document.getChunkCount());
        assertNotNull(document.getErrorMessage());
        verify(documentMapper).updateById(document);
    }

    @Test
    void staleCallbackDoesNotMutateCurrentJob() {
        Document document = ownedDocument(DocumentStatus.PROCESSING);
        DocumentIndexJob job = job("current-version", "PROCESSING", 0);
        DocumentIndexCallbackDTO callback = callback("COMPLETED", "old-version", 0);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(documentIndexJobMapper.selectLatestByDocumentId(10L)).thenReturn(job);

        vectorizationService.updateDocumentStatus(10L, callback);

        verify(documentMapper, never()).updateById(document);
        verify(documentIndexJobMapper, never()).updateById(job);
    }

    @Test
    void callbackRejectsUnknownStatus() {
        Document document = ownedDocument(DocumentStatus.PROCESSING);
        DocumentIndexJob job = job("version-1", "PROCESSING", 0);
        DocumentIndexCallbackDTO callback = callback("UNKNOWN", "version-1", 0);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(documentIndexJobMapper.selectLatestByDocumentId(10L)).thenReturn(job);

        assertThrows(BusinessException.class, () -> vectorizationService.updateDocumentStatus(10L, callback));
    }

    @Test
    void completedCallbackRequiresAllChunkMetadata() {
        Document document = ownedDocument(DocumentStatus.PROCESSING);
        DocumentIndexJob job = job("version-1", "PROCESSING", 0);
        DocumentIndexCallbackDTO callback = callback("COMPLETED", "version-1", 2);
        callback.setChunks(List.of(chunk("chunk-1", 0)));
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(documentIndexJobMapper.selectLatestByDocumentId(10L)).thenReturn(job);

        assertThrows(BusinessException.class, () -> vectorizationService.updateDocumentStatus(10L, callback));
        verify(documentChunkMapper, never()).deleteByDocumentId(10L);
    }

    @Test
    void completedCallbackPersistsChunksAndCompletesJob() {
        Document document = ownedDocument(DocumentStatus.PROCESSING);
        DocumentIndexJob job = job("version-1", "PROCESSING", 0);
        DocumentIndexCallbackDTO callback = callback("COMPLETED", "version-1", 1);
        callback.setChunks(List.of(chunk("chunk-1", 0)));
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(documentIndexJobMapper.selectLatestByDocumentId(10L)).thenReturn(job);

        vectorizationService.updateDocumentStatus(10L, callback);

        assertEquals(DocumentStatus.COMPLETED.getCode(), document.getStatus());
        assertEquals(1, document.getChunkCount());
        assertNotNull(document.getProcessedAt());
        assertEquals("COMPLETED", job.getStatus());
        assertNotNull(job.getCompletedAt());
        verify(documentChunkMapper).deleteByDocumentId(10L);
        verify(documentChunkMapper).insert(any());
        verify(documentMapper).updateById(document);
        verify(documentIndexJobMapper).updateById(job);
    }

    @Test
    void failedCallbackTruncatesStoredErrorMessages() {
        Document document = ownedDocument(DocumentStatus.PROCESSING);
        DocumentIndexJob job = job("version-1", "PROCESSING", 0);
        DocumentIndexCallbackDTO callback = callback("FAILED", "version-1", 0);
        callback.setMessage("x".repeat(1200));
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(documentIndexJobMapper.selectLatestByDocumentId(10L)).thenReturn(job);

        vectorizationService.updateDocumentStatus(10L, callback);

        assertEquals(500, document.getErrorMessage().length());
        assertEquals(1000, job.getErrorMessage().length());
        assertEquals("FAILED", job.getStatus());
    }

    @Test
    void taskStatusUsesDocumentStateBeforeFirstIndexJob() throws Exception {
        Document document = ownedDocument(DocumentStatus.PENDING);
        document.setChunkCount(null);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(ownedKnowledgeBase());
        when(documentIndexJobMapper.selectLatestByDocumentId(10L)).thenReturn(null);
        when(documentChunkMapper.countByDocumentId(10L, null)).thenReturn(0L);

        JsonNode response = objectMapper.readTree(vectorizationService.getTaskStatus(10L));

        assertEquals("PENDING", response.get("status").asText());
        assertEquals("queued", response.get("stage").asText());
        assertEquals(0, response.get("progress").asInt());
        assertEquals(0, response.get("chunks_count").asInt());
    }

    @Test
    void taskStatusDowngradesCompletedJobWhenPersistedChunksAreMissing() throws Exception {
        Document document = ownedDocument(DocumentStatus.COMPLETED);
        document.setChunkCount(3);
        DocumentIndexJob job = job("version-1", "COMPLETED", 3);
        job.setCompletedAt(LocalDateTime.now());
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(ownedKnowledgeBase());
        when(documentIndexJobMapper.selectLatestByDocumentId(10L)).thenReturn(job);
        when(documentChunkMapper.countByDocumentId(10L, null)).thenReturn(0L);

        JsonNode response = objectMapper.readTree(vectorizationService.getTaskStatus(10L));

        assertEquals("PENDING", response.get("status").asText());
        assertEquals(0, response.get("chunks_count").asInt());
        assertEquals("queued", response.get("stage").asText());
    }

    @Test
    void syncAllRejectsAnonymousRequest() {
        jwtUtilsMock.when(JwtUtils::isLogin).thenReturn(false);

        assertThrows(BusinessException.class, vectorizationService::syncAllDocuments);
    }

    @Test
    void syncAllReturnsZeroWhenUserHasNoKnowledgeBases() {
        when(knowledgeBaseMapper.selectList(any())).thenReturn(List.of());

        assertEquals(0, vectorizationService.syncAllDocuments());
        verify(documentMapper, never()).selectList(any());
    }

    @Test
    void completedCallbackCopiesChunkMetadata() {
        Document document = ownedDocument(DocumentStatus.PROCESSING);
        DocumentIndexJob job = job("version-1", "PROCESSING", 0);
        DocumentChunkCallbackDTO chunk = chunk("chunk-1", 2);
        chunk.setOutlinePath(List.of("Chapter", "Section"));
        chunk.setMetadata(Map.of("page", 3));
        DocumentIndexCallbackDTO callback = callback("COMPLETED", "version-1", 1);
        callback.setChunks(List.of(chunk));
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(documentIndexJobMapper.selectLatestByDocumentId(10L)).thenReturn(job);
        ArgumentCaptor<com.hfusionhub.entity.DocumentChunk> captor =
                ArgumentCaptor.forClass(com.hfusionhub.entity.DocumentChunk.class);

        assertDoesNotThrow(() -> vectorizationService.updateDocumentStatus(10L, callback));

        verify(documentChunkMapper).insert(captor.capture());
        assertEquals("chunk-1", captor.getValue().getChunkId());
        assertEquals(2, captor.getValue().getChunkIndex());
        assertEquals("[\"Chapter\",\"Section\"]", captor.getValue().getOutlinePath());
        assertEquals("{\"page\":3}", captor.getValue().getMetadata());
    }

    // -------------------- 分块详情 --------------------

    @Test
    void getChunkDetailReturnsTypedDTOWhenChunkExists() {
        Document document = ownedDocument(DocumentStatus.COMPLETED);
        DocumentChunk persistedChunk =
                persistedChunk("chunk-a1", 10L, 0, "text", "Key finding: the revenue grew by 42%");
        persistedChunk.setOutlinePath("[\"Summary\"]");
        persistedChunk.setMetadata("{\"tokens\": 128}");
        when(documentChunkMapper.selectByChunkId("chunk-a1")).thenReturn(persistedChunk);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(ownedKnowledgeBase());

        ChunkDTO result = vectorizationService.getChunkDetail("chunk-a1");

        assertEquals("chunk-a1", result.getChunkId());
        assertEquals(10L, result.getDocumentId());
        assertEquals(0, result.getIndex());
        assertEquals("text", result.getBlockType());
        assertEquals("Key finding: the revenue grew by 42%", result.getContent());
        assertEquals(List.of("Summary"), result.getOutlinePath());
        assertEquals(Map.of("tokens", 128), result.getMetadata());
    }

    @Test
    void getChunkDetailThrowsNotFoundWhenChunkMissing() {
        when(documentChunkMapper.selectByChunkId("nonexistent")).thenReturn(null);

        BusinessException ex =
                assertThrows(BusinessException.class, () -> vectorizationService.getChunkDetail("nonexistent"));

        assertEquals(StatusCode.CHUNK_NOT_FOUND, ex.getCode());
        assertEquals("分块不存在", ex.getMessage());
    }

    @Test
    void getChunkDetailValidatesDocumentOwnership() {
        DocumentChunk persistedChunk = persistedChunk("chunk-a1", 10L, 0, "text", "content");
        when(documentChunkMapper.selectByChunkId("chunk-a1")).thenReturn(persistedChunk);
        // Document owned by user 1
        Document document = ownedDocument(DocumentStatus.COMPLETED);
        when(documentMapper.selectById(10L)).thenReturn(document);
        // But the logged-in user is 999 — not the owner
        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(20L);
        kb.setUserId(999L);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(kb);

        assertThrows(BusinessException.class, () -> vectorizationService.getChunkDetail("chunk-a1"));
    }

    @Test
    void getChunkDetailThrowsWhenDocumentOfChunkIsMissing() {
        DocumentChunk persistedChunk = persistedChunk("chunk-a1", 99L, 0, "text", "orphan");
        when(documentChunkMapper.selectByChunkId("chunk-a1")).thenReturn(persistedChunk);
        when(documentMapper.selectById(99L)).thenReturn(null);

        assertThrows(BusinessException.class, () -> vectorizationService.getChunkDetail("chunk-a1"));
    }

    @Test
    void getChunkDetailUsesExplicitSelectByChunkId() {
        // 验证不依赖 MyBatis Plus selectById
        Document document = ownedDocument(DocumentStatus.COMPLETED);
        DocumentChunk persistedChunk = persistedChunk("chunk-b2", 10L, 1, "code", "print('hello')");
        when(documentChunkMapper.selectByChunkId("chunk-b2")).thenReturn(persistedChunk);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(ownedKnowledgeBase());

        ChunkDTO result = vectorizationService.getChunkDetail("chunk-b2");

        assertEquals("chunk-b2", result.getChunkId());
        assertEquals("code", result.getBlockType());
        // confirm the explicit mapper method was called, not selectById
        verify(documentChunkMapper).selectByChunkId("chunk-b2");
    }

    @Test
    void headerlessCallbackResolvesDocumentTenantAndSettlesIndexChunkUsage() {
        Document document = ownedDocument(DocumentStatus.PROCESSING);
        DocumentIndexJob job = job("version-1", "PROCESSING", 0);
        DocumentIndexCallbackDTO callback = callback("COMPLETED", "version-1", 2);
        callback.setChunks(List.of(chunk("chunk-1", 0), chunk("chunk-2", 1)));
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(documentIndexJobMapper.selectLatestByDocumentId(10L)).thenReturn(job);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(ownedKnowledgeBase());
        when(userMapper.selectById(1L)).thenReturn(ownerUser(7L));

        vectorizationService.updateDocumentStatus(10L, callback);

        verify(usageLedgerService)
                .settle(
                        eq(UsageMeter.INDEX_CHUNKS),
                        eq("INDEX_CHUNKS:version-1"),
                        eq(2L),
                        eq("document_index"),
                        eq("10"));
        assertNull(TenantContext.getTenantId());
    }

    @Test
    void failedCallbackReleasesIndexChunkUsage() {
        Document document = ownedDocument(DocumentStatus.PROCESSING);
        DocumentIndexJob job = job("version-1", "PROCESSING", 0);
        DocumentIndexCallbackDTO callback = callback("FAILED", "version-1", 0);
        callback.setMessage("embedding failure");
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(documentIndexJobMapper.selectLatestByDocumentId(10L)).thenReturn(job);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(ownedKnowledgeBase());
        when(userMapper.selectById(1L)).thenReturn(ownerUser(7L));

        vectorizationService.updateDocumentStatus(10L, callback);

        verify(usageLedgerService).release(eq(UsageMeter.INDEX_CHUNKS), eq("INDEX_CHUNKS:version-1"));
        verify(usageLedgerService, never()).settle(any(), any(), anyLong(), any(), any());
    }

    @Test
    void startVectorizationReservesIndexChunksOnEstimatedUpperBound() throws Exception {
        java.nio.file.Path tempFile = java.nio.file.Files.createTempFile("vec-meta", ".md");
        try {
            Document document = ownedDocument(DocumentStatus.PENDING);
            document.setFilePath(tempFile.toString());
            document.setFileSize(30000L);
            KnowledgeBase kb = ownedKnowledgeBase();
            when(documentMapper.selectById(10L)).thenReturn(document);
            when(knowledgeBaseMapper.selectById(20L)).thenReturn(kb);
            when(userMapper.selectById(1L)).thenReturn(ownerUser(7L));
            when(documentIndexJobMapper.selectMaxAttemptByDocumentId(10L)).thenReturn(0);
            org.mockito.Mockito.doReturn(
                            new org.springframework.http.ResponseEntity<>("ok", org.springframework.http.HttpStatus.OK))
                    .when(restTemplate)
                    .exchange(
                            org.mockito.ArgumentMatchers.anyString(),
                            org.mockito.ArgumentMatchers.any(),
                            org.mockito.ArgumentMatchers.any(),
                            eq(String.class));
            ArgumentCaptor<com.hfusionhub.entity.DocumentIndexJob> jobCaptor =
                    ArgumentCaptor.forClass(com.hfusionhub.entity.DocumentIndexJob.class);

            vectorizationService.startVectorization(10L, "ollama");

            verify(documentIndexJobMapper).insert(jobCaptor.capture());
            String version = jobCaptor.getValue().getIndexVersion();
            // 30000 bytes / 300 bytes-per-chunk = 100 chunks reserved
            ArgumentCaptor<Long> amountCaptor = ArgumentCaptor.forClass(Long.class);
            verify(usageLedgerService)
                    .reserve(
                            eq(UsageMeter.INDEX_CHUNKS),
                            eq("INDEX_CHUNKS:" + version),
                            amountCaptor.capture(),
                            eq("document_index"),
                            eq("10"));
            assertEquals(100L, amountCaptor.getValue());
        } finally {
            java.nio.file.Files.deleteIfExists(tempFile);
        }
    }

    @Test
    void startVectorizationReservesCeilingChunksWhenFileSizeNotDivisible() throws Exception {
        // P0: 预占必须是上界 — 301 bytes / 300 bytes-per-chunk = ceil(301/300) = 2，
        // 整数除法 1 会低估预占，令索引越过额度门槛。
        java.nio.file.Path tempFile = java.nio.file.Files.createTempFile("vec-ceil", ".md");
        try {
            Document document = ownedDocument(DocumentStatus.PENDING);
            document.setFilePath(tempFile.toString());
            document.setFileSize(301L);
            KnowledgeBase kb = ownedKnowledgeBase();
            when(documentMapper.selectById(10L)).thenReturn(document);
            when(knowledgeBaseMapper.selectById(20L)).thenReturn(kb);
            when(userMapper.selectById(1L)).thenReturn(ownerUser(7L));
            when(documentIndexJobMapper.selectMaxAttemptByDocumentId(10L)).thenReturn(0);
            org.mockito.Mockito.doReturn(
                            new org.springframework.http.ResponseEntity<>("ok", org.springframework.http.HttpStatus.OK))
                    .when(restTemplate)
                    .exchange(
                            org.mockito.ArgumentMatchers.anyString(),
                            org.mockito.ArgumentMatchers.any(),
                            org.mockito.ArgumentMatchers.any(),
                            eq(String.class));
            ArgumentCaptor<com.hfusionhub.entity.DocumentIndexJob> jobCaptor =
                    ArgumentCaptor.forClass(com.hfusionhub.entity.DocumentIndexJob.class);

            vectorizationService.startVectorization(10L, "ollama");

            verify(documentIndexJobMapper).insert(jobCaptor.capture());
            String version = jobCaptor.getValue().getIndexVersion();
            ArgumentCaptor<Long> amountCaptor = ArgumentCaptor.forClass(Long.class);
            verify(usageLedgerService)
                    .reserve(
                            eq(UsageMeter.INDEX_CHUNKS),
                            eq("INDEX_CHUNKS:" + version),
                            amountCaptor.capture(),
                            eq("document_index"),
                            eq("10"));
            assertEquals(2L, amountCaptor.getValue());
        } finally {
            java.nio.file.Files.deleteIfExists(tempFile);
        }
    }

    @Test
    void missingSourceFileMarksDocumentAndProcessingJobsFailed() {
        // 源文件缺失是确定性失败：文档标记 FAILED，历史 PROCESSING job 也一并
        // 标记 FAILED，否则 DocumentIndexRecoveryScheduler 无限重试（job 永不退出 PROCESSING）。
        Document document = ownedDocument(DocumentStatus.PROCESSING);
        document.setFilePath(null); // 源文件路径为空
        KnowledgeBase kb = ownedKnowledgeBase();
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(kb);

        BusinessException ex =
                assertThrows(BusinessException.class, () -> vectorizationService.startVectorization(10L, "ollama"));

        // 文档被标记为 FAILED(3)
        assertEquals(DocumentStatus.FAILED.getCode(), document.getStatus());
        assertEquals(0, document.getChunkCount());
        assertTrue(ex.getMessage().contains("源文件"));
        // PROCESSING job 被更新为 FAILED
        verify(documentIndexJobMapper)
                .update(org.mockito.ArgumentMatchers.isNull(), org.mockito.ArgumentMatchers.argThat(wrapper -> {
                    var update = new com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper<
                            com.hfusionhub.entity.DocumentIndexJob>();
                    return wrapper.getClass().isAssignableFrom(update.getClass());
                }));
    }

    @Test
    void recoveryMarksDocumentAndProcessingJobsFailedWhenKnowledgeBaseDeleted() {
        // 恢复路径（enforceRequestOwner=false）下知识库已删除（selectById 逻辑删除
        // 过滤后返回 null）是确定性失败：文档 + PROCESSING job 一并标记 FAILED，
        // 否则 DocumentIndexRecoveryScheduler 每 5 分钟无限重试，日志持续刷「恢复索引任务失败」。
        Document document = ownedDocument(DocumentStatus.PROCESSING);
        DocumentIndexJob staleJob = job("version-stale", "PROCESSING", 0);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(null); // KB 已逻辑删除
        when(documentIndexJobMapper.selectStaleProcessingJobs(any(), anyInt())).thenReturn(List.of(staleJob));

        vectorizationService.recoverStaleIndexJobs();

        // 文档被标记为 FAILED(3)
        assertEquals(DocumentStatus.FAILED.getCode(), document.getStatus());
        assertEquals(0, document.getChunkCount());
        // PROCESSING job 被更新为 FAILED
        verify(documentIndexJobMapper)
                .update(org.mockito.ArgumentMatchers.isNull(), org.mockito.ArgumentMatchers.argThat(wrapper -> {
                    var update = new com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper<
                            com.hfusionhub.entity.DocumentIndexJob>();
                    return wrapper.getClass().isAssignableFrom(update.getClass());
                }));
    }

    @Test
    void deleteDocumentIndexUsesDocumentTenantAfterLogicalDeletion() {
        Document document = ownedDocument(DocumentStatus.PENDING);
        document.setDeleted(1);
        KnowledgeBase knowledgeBase = ownedKnowledgeBase();
        knowledgeBase.setDeleted(1);
        when(documentMapper.selectIncludingDeleted(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectIncludingDeleted(20L)).thenReturn(knowledgeBase);
        when(userMapper.selectById(1L)).thenReturn(ownerUser(7L));
        org.mockito.Mockito.doReturn(new ResponseEntity<>("ok", HttpStatus.OK))
                .when(restTemplate)
                .exchange(
                        eq("http://localhost:9000/api/documents/10/chunks"),
                        eq(HttpMethod.DELETE),
                        org.mockito.ArgumentMatchers.any(HttpEntity.class),
                        eq(String.class));

        vectorizationService.deleteDocumentIndex(10L);

        ArgumentCaptor<HttpEntity> requestCaptor = ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate)
                .exchange(
                        eq("http://localhost:9000/api/documents/10/chunks"),
                        eq(HttpMethod.DELETE),
                        requestCaptor.capture(),
                        eq(String.class));
        assertEquals("7", requestCaptor.getValue().getHeaders().getFirst("X-Tenant-Id"));
        verify(documentChunkMapper).deleteByDocumentId(10L);
    }

    private User ownerUser(Long tenantId) {
        User user = new User();
        user.setId(1L);
        user.setTenantId(tenantId);
        return user;
    }

    private Document ownedDocument(DocumentStatus status) {
        Document document = new Document();
        document.setId(10L);
        document.setKnowledgeBaseId(20L);
        document.setTitle("Document");
        document.setFileType(".md");
        document.setFileSize(1024L);
        document.setStatus(status.getCode());
        return document;
    }

    private KnowledgeBase ownedKnowledgeBase() {
        KnowledgeBase knowledgeBase = new KnowledgeBase();
        knowledgeBase.setId(20L);
        knowledgeBase.setUserId(1L);
        knowledgeBase.setStatus(0);
        return knowledgeBase;
    }

    private DocumentIndexJob job(String version, String status, int chunkCount) {
        DocumentIndexJob job = new DocumentIndexJob();
        job.setId(30L);
        job.setDocumentId(10L);
        job.setKnowledgeBaseId(20L);
        job.setIndexVersion(version);
        job.setStatus(status);
        job.setChunkCount(chunkCount);
        job.setStartedAt(LocalDateTime.now().minusSeconds(5));
        return job;
    }

    private DocumentIndexCallbackDTO callback(String status, String version, int chunkCount) {
        DocumentIndexCallbackDTO callback = new DocumentIndexCallbackDTO();
        callback.setStatus(status);
        callback.setIndexVersion(version);
        callback.setChunkCount(chunkCount);
        callback.setChunks(List.of());
        return callback;
    }

    private DocumentChunkCallbackDTO chunk(String chunkId, int index) {
        DocumentChunkCallbackDTO chunk = new DocumentChunkCallbackDTO();
        chunk.setChunkId(chunkId);
        chunk.setIndex(index);
        chunk.setBlockType("text");
        chunk.setContentExcerpt("Chunk content");
        chunk.setCharCount(13);
        return chunk;
    }

    private DocumentChunk persistedChunk(
            String chunkId, Long documentId, int index, String blockType, String contentExcerpt) {
        DocumentChunk entity = new DocumentChunk();
        entity.setChunkId(chunkId);
        entity.setDocumentId(documentId);
        entity.setKnowledgeBaseId(20L);
        entity.setIndexVersion("v1");
        entity.setChunkIndex(index);
        entity.setBlockType(blockType);
        entity.setContentExcerpt(contentExcerpt);
        entity.setCharCount(contentExcerpt.length());
        entity.setOutlinePath("[]");
        entity.setMetadata("{}");
        return entity;
    }

    // ── 向量库对账 ─────────────────────────────────────────────────────────

    private java.util.Map<String, Object> globalCountRow(Long tenantId, Long kbId, Long cnt) {
        return java.util.Map.of("tenant_id", tenantId, "knowledge_base_id", kbId, "cnt", cnt);
    }

    @Test
    void reconcileReturnsZeroWhenNoChunkData() {
        when(documentChunkMapper.countGroupByTenantAndKnowledgeBase()).thenReturn(List.of());

        assertEquals(0, vectorizationService.reconcileVectorCounts());
        org.mockito.Mockito.verifyNoInteractions(restTemplate);
    }

    @Test
    void reconcileReportsNoMismatchWhenCountsAgree() {
        when(documentChunkMapper.countGroupByTenantAndKnowledgeBase()).thenReturn(List.of(globalCountRow(7L, 20L, 3L)));
        when(restTemplate.exchange(any(String.class), eq(HttpMethod.POST), any(HttpEntity.class), eq(String.class)))
                .thenReturn(new ResponseEntity<>("{\"counts\":{\"20\":3}}", HttpStatus.OK));

        assertEquals(0, vectorizationService.reconcileVectorCounts());
    }

    @Test
    void reconcileReportsMismatchWhenMilvusEmptyButChunksPersisted() {
        // 容器重建 → 向量库清空但 MySQL 残留 chunk 元数据 —— 必须显式告警。
        when(documentChunkMapper.countGroupByTenantAndKnowledgeBase()).thenReturn(List.of(globalCountRow(7L, 20L, 3L)));
        when(restTemplate.exchange(any(String.class), eq(HttpMethod.POST), any(HttpEntity.class), eq(String.class)))
                .thenReturn(new ResponseEntity<>("{\"counts\":{\"20\":0}}", HttpStatus.OK));

        assertEquals(1, vectorizationService.reconcileVectorCounts());
    }

    @Test
    void reconcileSkipsKbWhenPythonMarkedUnavailable() {
        // Milvus 查询失败标记 -1 —— 不误报为失配。
        when(documentChunkMapper.countGroupByTenantAndKnowledgeBase()).thenReturn(List.of(globalCountRow(7L, 20L, 3L)));
        when(restTemplate.exchange(any(String.class), eq(HttpMethod.POST), any(HttpEntity.class), eq(String.class)))
                .thenReturn(new ResponseEntity<>("{\"counts\":{\"20\":-1}}", HttpStatus.OK));

        assertEquals(0, vectorizationService.reconcileVectorCounts());
    }

    @Test
    void startVectorizationLocksDocumentAndComputesAttemptFromMax() throws Exception {
        // V77/S5: 文档级行锁 + MAX(attempt)+1 + 旧 PROCESSING job 被 supersede
        java.nio.file.Path tempFile = java.nio.file.Files.createTempFile("vec-lock", ".md");
        try {
            Document document = ownedDocument(DocumentStatus.PROCESSING);
            document.setFilePath(tempFile.toString());
            document.setFileSize(300L);
            KnowledgeBase kb = ownedKnowledgeBase();
            DocumentIndexJob oldJob = job("version-old", "PROCESSING", 0);
            when(documentMapper.selectById(10L)).thenReturn(document);
            when(knowledgeBaseMapper.selectById(20L)).thenReturn(kb);
            when(userMapper.selectById(1L)).thenReturn(ownerUser(7L));
            when(documentIndexJobMapper.selectMaxAttemptByDocumentId(10L)).thenReturn(2);
            when(documentIndexJobMapper.selectList(any())).thenReturn(List.of(oldJob));
            org.mockito.Mockito.doReturn(
                            new org.springframework.http.ResponseEntity<>("ok", org.springframework.http.HttpStatus.OK))
                    .when(restTemplate)
                    .exchange(
                            org.mockito.ArgumentMatchers.anyString(),
                            org.mockito.ArgumentMatchers.any(),
                            org.mockito.ArgumentMatchers.any(),
                            eq(String.class));
            ArgumentCaptor<DocumentIndexJob> jobCaptor = ArgumentCaptor.forClass(DocumentIndexJob.class);

            vectorizationService.startVectorization(10L, "ollama");

            verify(documentMapper).selectByIdForUpdate(10L);
            verify(documentIndexJobMapper).insert(jobCaptor.capture());
            assertEquals(3, jobCaptor.getValue().getAttempt());
            verify(usageLedgerService).release(eq(UsageMeter.INDEX_CHUNKS), eq("INDEX_CHUNKS:version-old"));
        } finally {
            java.nio.file.Files.deleteIfExists(tempFile);
        }
    }

}
