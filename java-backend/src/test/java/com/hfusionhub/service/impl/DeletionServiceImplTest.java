package com.hfusionhub.service.impl;

import com.hfusionhub.entity.DeletionTask;
import com.hfusionhub.entity.Document;
import com.hfusionhub.mapper.ConversationMapper;
import com.hfusionhub.mapper.DeletionTaskMapper;
import com.hfusionhub.mapper.DocumentChunkMapper;
import com.hfusionhub.mapper.DocumentIndexJobMapper;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.MessageMapper;
import com.hfusionhub.service.VectorizationService;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.doThrow;

class DeletionServiceImplTest {

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
}
