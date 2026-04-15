package com.hfusionhub.service.impl;

import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.entity.DeletionTask;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.enums.DocumentStatus;
import com.hfusionhub.mapper.ConversationMapper;
import com.hfusionhub.mapper.DeletionTaskMapper;
import com.hfusionhub.mapper.DocumentChunkMapper;
import com.hfusionhub.mapper.DocumentIndexJobMapper;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.MessageMapper;
import com.hfusionhub.service.VectorizationService;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.times;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;

class DeletionServiceImplTest {

    @Test
    void getPendingTasksRecoversStaleProcessingTasksBeforeSelectingPending() {
        DeletionTaskMapper deletionTaskMapper = mock(DeletionTaskMapper.class);
        KnowledgeBaseMapper knowledgeBaseMapper = mock(KnowledgeBaseMapper.class);
        DocumentMapper documentMapper = mock(DocumentMapper.class);
        DocumentChunkMapper documentChunkMapper = mock(DocumentChunkMapper.class);
        DocumentIndexJobMapper documentIndexJobMapper = mock(DocumentIndexJobMapper.class);
        ConversationMapper conversationMapper = mock(ConversationMapper.class);
        MessageMapper messageMapper = mock(MessageMapper.class);
        VectorizationService vectorizationService = mock(VectorizationService.class);

        DeletionServiceImpl service = new DeletionServiceImpl(
                deletionTaskMapper,
                knowledgeBaseMapper,
                documentMapper,
                documentChunkMapper,
                documentIndexJobMapper,
                conversationMapper,
                messageMapper,
                vectorizationService);

        DeletionTask pending = new DeletionTask();
        pending.setId(99L);
        when(deletionTaskMapper.recoverStaleProcessingTasks(
                any(LocalDateTime.class),
                eq("任务执行超时，已恢复为可重试状态")))
                .thenReturn(1);
        when(deletionTaskMapper.selectPendingTasks(10)).thenReturn(List.of(pending));

        List<DeletionTask> tasks = service.getPendingTasks();

        assertEquals(List.of(pending), tasks);
        verify(deletionTaskMapper).recoverStaleProcessingTasks(
                any(LocalDateTime.class),
                eq("任务执行超时，已恢复为可重试状态"));
        verify(deletionTaskMapper).selectPendingTasks(10);
    }

    @Test
    void markFailedMarksKbDeleteFailedWhenRetriesExhausted() {
        DeletionTaskMapper deletionTaskMapper = mock(DeletionTaskMapper.class);
        KnowledgeBaseMapper knowledgeBaseMapper = mock(KnowledgeBaseMapper.class);
        DocumentMapper documentMapper = mock(DocumentMapper.class);
        DocumentChunkMapper documentChunkMapper = mock(DocumentChunkMapper.class);
        DocumentIndexJobMapper documentIndexJobMapper = mock(DocumentIndexJobMapper.class);
        ConversationMapper conversationMapper = mock(ConversationMapper.class);
        MessageMapper messageMapper = mock(MessageMapper.class);
        VectorizationService vectorizationService = mock(VectorizationService.class);

        DeletionServiceImpl service = new DeletionServiceImpl(
                deletionTaskMapper,
                knowledgeBaseMapper,
                documentMapper,
                documentChunkMapper,
                documentIndexJobMapper,
                conversationMapper,
                messageMapper,
                vectorizationService);

        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(11L);
        kb.setStatus(CommonConstants.KB_STATUS_DELETING);
        when(knowledgeBaseMapper.selectById(11L)).thenReturn(kb);

        DeletionTask task = new DeletionTask();
        task.setTaskType("KB_DELETE");
        task.setTargetId(11L);
        task.setRetryCount(4);
        task.setMaxRetries(5);

        service.markFailed(task, "vector cleanup failed");

        assertEquals("FAILED", task.getStatus());
        assertEquals(5, task.getRetryCount());
        assertEquals(CommonConstants.KB_STATUS_DELETE_FAILED, kb.getStatus());
        verify(knowledgeBaseMapper).updateById(kb);
        verify(deletionTaskMapper).updateById(task);
    }

    @Test
    void documentDeleteContinuesWhenVectorDeletionFails() {
        DeletionTaskMapper deletionTaskMapper = mock(DeletionTaskMapper.class);
        KnowledgeBaseMapper knowledgeBaseMapper = mock(KnowledgeBaseMapper.class);
        DocumentMapper documentMapper = mock(DocumentMapper.class);
        DocumentChunkMapper documentChunkMapper = mock(DocumentChunkMapper.class);
        DocumentIndexJobMapper documentIndexJobMapper = mock(DocumentIndexJobMapper.class);
        ConversationMapper conversationMapper = mock(ConversationMapper.class);
        MessageMapper messageMapper = mock(MessageMapper.class);
        VectorizationService vectorizationService = mock(VectorizationService.class);

        DeletionServiceImpl service = new DeletionServiceImpl(
                deletionTaskMapper,
                knowledgeBaseMapper,
                documentMapper,
                documentChunkMapper,
                documentIndexJobMapper,
                conversationMapper,
                messageMapper,
                vectorizationService);

        Document document = new Document();
        document.setId(7L);
        when(documentMapper.selectById(7L)).thenReturn(document);
        doThrow(new RuntimeException("vector store unavailable"))
                .when(vectorizationService).deleteDocumentIndex(7L);

        DeletionTask task = new DeletionTask();
        task.setTaskType("DOCUMENT_DELETE");
        task.setTargetId(7L);
        task.setStatus("PENDING");
        task.setStepIndex(0);
        task.setRetryCount(0);
        task.setMaxRetries(5);

        service.executeStep(task);

        verify(vectorizationService).deleteDocumentIndex(7L);
        assertEquals("PENDING", task.getStatus());
        assertEquals("VECTORS_DELETED", task.getStep());
        assertEquals(1, task.getStepIndex());
    }

    @Test
    void documentPurgeContinuesWhenVectorDeletionFails() {
        DeletionTaskMapper deletionTaskMapper = mock(DeletionTaskMapper.class);
        KnowledgeBaseMapper knowledgeBaseMapper = mock(KnowledgeBaseMapper.class);
        DocumentMapper documentMapper = mock(DocumentMapper.class);
        DocumentChunkMapper documentChunkMapper = mock(DocumentChunkMapper.class);
        DocumentIndexJobMapper documentIndexJobMapper = mock(DocumentIndexJobMapper.class);
        ConversationMapper conversationMapper = mock(ConversationMapper.class);
        MessageMapper messageMapper = mock(MessageMapper.class);
        VectorizationService vectorizationService = mock(VectorizationService.class);

        DeletionServiceImpl service = new DeletionServiceImpl(
                deletionTaskMapper,
                knowledgeBaseMapper,
                documentMapper,
                documentChunkMapper,
                documentIndexJobMapper,
                conversationMapper,
                messageMapper,
                vectorizationService);

        Document document = new Document();
        document.setId(7L);
        document.setDeleted(1);
        when(documentMapper.selectIncludingDeleted(7L)).thenReturn(document);
        doThrow(new RuntimeException("vector store unavailable"))
                .when(vectorizationService).deleteDocumentIndex(7L);

        DeletionTask task = new DeletionTask();
        task.setTaskType("DOCUMENT_PURGE");
        task.setTargetId(7L);
        task.setStatus("PENDING");
        task.setStepIndex(0);
        task.setRetryCount(0);
        task.setMaxRetries(5);

        service.executeStep(task);

        verify(vectorizationService).deleteDocumentIndex(7L);
        assertEquals("PENDING", task.getStatus());
        assertEquals("VECTORS_DELETED", task.getStep());
        assertEquals(1, task.getStepIndex());
    }

    @Test
    void documentDeleteMarksDocumentAsRecycledWithoutDeletingTheFile() {
        DeletionTaskMapper deletionTaskMapper = mock(DeletionTaskMapper.class);
        KnowledgeBaseMapper knowledgeBaseMapper = mock(KnowledgeBaseMapper.class);
        DocumentMapper documentMapper = mock(DocumentMapper.class);
        DocumentChunkMapper documentChunkMapper = mock(DocumentChunkMapper.class);
        DocumentIndexJobMapper documentIndexJobMapper = mock(DocumentIndexJobMapper.class);
        ConversationMapper conversationMapper = mock(ConversationMapper.class);
        MessageMapper messageMapper = mock(MessageMapper.class);
        VectorizationService vectorizationService = mock(VectorizationService.class);

        DeletionServiceImpl service = new DeletionServiceImpl(
                deletionTaskMapper,
                knowledgeBaseMapper,
                documentMapper,
                documentChunkMapper,
                documentIndexJobMapper,
                conversationMapper,
                messageMapper,
                vectorizationService);

        Document document = new Document();
        document.setId(7L);
        when(documentMapper.selectById(7L)).thenReturn(document);
        when(documentMapper.markRecycled(any(), any(), any(), any(), any())).thenReturn(1);

        DeletionTask task = new DeletionTask();
        task.setTaskType("DOCUMENT_DELETE");
        task.setTargetId(7L);
        task.setStatus("PENDING");
        task.setStepIndex(3);

        service.executeStep(task);

        verify(documentMapper).markRecycled(
                any(),
                any(),
                any(),
                org.mockito.ArgumentMatchers.eq(0),
                any());
        assertEquals("PENDING", task.getStatus());
        assertEquals("DOCUMENT_RECYCLED", task.getStep());
        assertEquals(4, task.getStepIndex());
    }

    @Test
    void kbDisableClearsIndexesAndResetsLiveDocuments() {
        DeletionTaskMapper deletionTaskMapper = mock(DeletionTaskMapper.class);
        KnowledgeBaseMapper knowledgeBaseMapper = mock(KnowledgeBaseMapper.class);
        DocumentMapper documentMapper = mock(DocumentMapper.class);
        DocumentChunkMapper documentChunkMapper = mock(DocumentChunkMapper.class);
        DocumentIndexJobMapper documentIndexJobMapper = mock(DocumentIndexJobMapper.class);
        ConversationMapper conversationMapper = mock(ConversationMapper.class);
        MessageMapper messageMapper = mock(MessageMapper.class);
        VectorizationService vectorizationService = mock(VectorizationService.class);

        DeletionServiceImpl service = new DeletionServiceImpl(
                deletionTaskMapper,
                knowledgeBaseMapper,
                documentMapper,
                documentChunkMapper,
                documentIndexJobMapper,
                conversationMapper,
                messageMapper,
                vectorizationService);

        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(11L);
        when(knowledgeBaseMapper.selectById(11L)).thenReturn(kb);

        Document liveDocument = new Document();
        liveDocument.setId(21L);
        liveDocument.setDeleted(0);
        liveDocument.setStatus(DocumentStatus.COMPLETED.getCode());
        liveDocument.setChunkCount(3);
        liveDocument.setProcessedAt(LocalDateTime.now());

        Document recycledDocument = new Document();
        recycledDocument.setId(22L);
        recycledDocument.setDeleted(1);
        recycledDocument.setStatus(DocumentStatus.COMPLETED.getCode());
        recycledDocument.setChunkCount(2);

        when(documentMapper.selectByKnowledgeBaseIncludingDeleted(11L))
                .thenReturn(List.of(liveDocument, recycledDocument));

        DeletionTask task = new DeletionTask();
        task.setTaskType("KB_DISABLE");
        task.setTargetId(11L);
        task.setStatus("PENDING");
        task.setStepIndex(0);
        task.setRetryCount(0);
        task.setMaxRetries(5);

        service.executeStep(task);
        verify(vectorizationService).deleteDocumentIndex(21L);
        verify(vectorizationService).deleteDocumentIndex(22L);
        verify(documentMapper).updateById(liveDocument);
        assertEquals(DocumentStatus.PENDING.getCode(), liveDocument.getStatus());
        assertEquals(0, liveDocument.getChunkCount());
        assertEquals(null, liveDocument.getProcessedAt());
        assertEquals("KB_DISABLE_VECTORS_DELETED", task.getStep());
        assertEquals(1, task.getStepIndex());

        service.executeStep(task);
        verify(documentChunkMapper).deleteByDocumentId(21L);
        verify(documentChunkMapper).deleteByDocumentId(22L);
        assertEquals("KB_DISABLE_CHUNKS_DELETED", task.getStep());
        assertEquals(2, task.getStepIndex());

        service.executeStep(task);
        verify(documentIndexJobMapper, times(2)).delete(any());
        assertEquals("KB_DISABLE_INDEX_JOBS_DELETED", task.getStep());
        assertEquals(3, task.getStepIndex());

        service.executeStep(task);
        verify(documentMapper, times(2)).updateById(liveDocument);
        assertEquals(DocumentStatus.PENDING.getCode(), liveDocument.getStatus());
        assertEquals(0, liveDocument.getChunkCount());
        assertEquals(null, liveDocument.getProcessedAt());
        assertEquals(DocumentStatus.COMPLETED.getCode(), recycledDocument.getStatus());
        assertEquals(2, recycledDocument.getChunkCount());
        assertEquals("KB_DISABLE_DOCUMENTS_RESET", task.getStep());
        assertEquals(4, task.getStepIndex());
    }
}
