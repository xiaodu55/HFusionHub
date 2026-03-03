package com.hfusionhub.service.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.DocumentChunkCallbackDTO;
import com.hfusionhub.dto.DocumentIndexCallbackDTO;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.DocumentIndexJob;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.enums.DocumentStatus;
import com.hfusionhub.mapper.DocumentChunkMapper;
import com.hfusionhub.mapper.DocumentIndexJobMapper;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.RestTemplate;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

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
    private RestTemplate restTemplate;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @InjectMocks
    private VectorizationServiceImpl vectorizationService;

    private MockedStatic<JwtUtils> jwtUtilsMock;

    @BeforeEach
    void setUp() {
        ReflectionTestUtils.setField(vectorizationService, "objectMapper", objectMapper);
        ReflectionTestUtils.setField(vectorizationService, "internalApiToken", "test-token");
        jwtUtilsMock = org.mockito.Mockito.mockStatic(JwtUtils.class);
        jwtUtilsMock.when(JwtUtils::isLogin).thenReturn(true);
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);
    }

    @AfterEach
    void tearDown() {
        jwtUtilsMock.close();
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

        assertThrows(BusinessException.class,
                () -> vectorizationService.updateDocumentStatus(10L, callback));
    }

    @Test
    void completedCallbackRequiresAllChunkMetadata() {
        Document document = ownedDocument(DocumentStatus.PROCESSING);
        DocumentIndexJob job = job("version-1", "PROCESSING", 0);
        DocumentIndexCallbackDTO callback = callback("COMPLETED", "version-1", 2);
        callback.setChunks(List.of(chunk("chunk-1", 0)));
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(documentIndexJobMapper.selectLatestByDocumentId(10L)).thenReturn(job);

        assertThrows(BusinessException.class,
                () -> vectorizationService.updateDocumentStatus(10L, callback));
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
}
