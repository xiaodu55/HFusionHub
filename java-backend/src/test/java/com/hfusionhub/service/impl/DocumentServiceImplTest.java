package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.DocumentUpdateDTO;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.enums.DocumentStatus;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.DeletionService;
import com.hfusionhub.service.VectorizationService;
import java.time.LocalDateTime;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class DocumentServiceImplTest {

    @Mock
    private DocumentMapper documentMapper;

    @Mock
    private KnowledgeBaseMapper knowledgeBaseMapper;

    @Mock
    private UserMapper userMapper;

    @Mock
    private VectorizationService vectorizationService;

    @Mock
    private DeletionService deletionService;

    @Mock
    private com.hfusionhub.service.KbShareService kbShareService;

    @InjectMocks
    private DocumentServiceImpl documentService;

    private MockedStatic<JwtUtils> jwtUtilsMock;

    @BeforeEach
    void setUp() {
        jwtUtilsMock = org.mockito.Mockito.mockStatic(JwtUtils.class);
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);
    }

    @AfterEach
    void tearDown() {
        jwtUtilsMock.close();
    }

    @Test
    void updateRejectsMissingDocument() {
        when(documentMapper.selectById(10L)).thenReturn(null);

        assertThrows(BusinessException.class, () -> documentService.update(10L, new DocumentUpdateDTO()));
        verify(knowledgeBaseMapper, never()).selectById(org.mockito.ArgumentMatchers.anyLong());
    }

    @Test
    void updateRejectsDocumentOwnedByAnotherUser() {
        Document document = document(10L, 20L, DocumentStatus.COMPLETED);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(knowledgeBase(20L, 2L));

        assertThrows(BusinessException.class, () -> documentService.update(10L, new DocumentUpdateDTO()));
        verify(documentMapper, never()).updateById(document);
    }

    @Test
    void titleOnlyUpdateKeepsExistingStatus() {
        Document document = document(10L, 20L, DocumentStatus.COMPLETED);
        DocumentUpdateDTO update = new DocumentUpdateDTO();
        update.setTitle("New title");
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(knowledgeBase(20L, 1L));

        documentService.update(10L, update);

        assertEquals("New title", document.getTitle());
        assertEquals(DocumentStatus.COMPLETED.getCode(), document.getStatus());
        verify(documentMapper).updateById(document);
    }

    @Test
    void contentUpdateMarksDocumentPendingForReindex() throws Exception {
        Document document = document(10L, 20L, DocumentStatus.COMPLETED);
        // A5：编辑内容回写源文件——文本类文档 + 真实临时文件验证同源语义
        document.setFileType("md");
        java.nio.file.Path sourceFile =
                java.nio.file.Files.createTempFile("doc-update-test", ".md");
        java.nio.file.Files.writeString(sourceFile, "original content");
        document.setFilePath(sourceFile.toString());
        DocumentUpdateDTO update = new DocumentUpdateDTO();
        update.setContent("Updated content");
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(knowledgeBase(20L, 1L));

        documentService.update(10L, update);

        assertEquals("Updated content", document.getContent());
        assertEquals("Updated content",
                java.nio.file.Files.readString(sourceFile));
        assertEquals(DocumentStatus.PENDING.getCode(), document.getStatus());
        verify(documentMapper, times(2)).updateById(document);
        java.nio.file.Files.deleteIfExists(sourceFile);
    }

    @Test
    void contentUpdateRejectsBinaryFileType() {
        Document document = document(10L, 20L, DocumentStatus.COMPLETED);
        document.setFileType("pdf");
        DocumentUpdateDTO update = new DocumentUpdateDTO();
        update.setContent("Updated content");
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(knowledgeBase(20L, 1L));

        // A5：二进制文档拒绝在线内容编辑（无法回写源文件，防索引与 DB 静默分叉）
        assertThrows(BusinessException.class, () -> documentService.update(10L, update));
        verify(documentMapper, never()).updateById(document);
    }

    @Test
    void deleteRejectsMissingDocument() {
        when(documentMapper.selectById(10L)).thenReturn(null);

        assertThrows(BusinessException.class, () -> documentService.delete(10L));
        verify(deletionService, never()).createTask("DOCUMENT_DELETE", 10L);
    }

    @Test
    void deleteRejectsDocumentOwnedByAnotherUser() {
        Document document = document(10L, 20L, DocumentStatus.COMPLETED);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(knowledgeBase(20L, 2L));

        assertThrows(BusinessException.class, () -> documentService.delete(10L));
        verify(deletionService, never()).createTask("DOCUMENT_DELETE", 10L);
    }

    @Test
    void repeatedDeleteIsIdempotentWhileDeletionIsInProgress() {
        Document document = document(10L, 20L, DocumentStatus.DELETING);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(knowledgeBase(20L, 1L));

        assertDoesNotThrow(() -> documentService.delete(10L));

        verify(documentMapper, never()).updateById(document);
        verify(deletionService, never()).createTask("DOCUMENT_DELETE", 10L);
    }

    @Test
    void deleteTransitionsDocumentAndCreatesOutboxTask() {
        Document document = document(10L, 20L, DocumentStatus.FAILED);
        document.setErrorMessage("old failure");
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(knowledgeBase(20L, 1L));

        documentService.delete(10L);

        assertEquals(DocumentStatus.DELETING.getCode(), document.getStatus());
        assertNull(document.getErrorMessage());
        verify(documentMapper).updateById(document);
        verify(deletionService).createTask("DOCUMENT_DELETE", 10L);
    }

    @Test
    void getContentReturnsContentForOwner() {
        Document document = document(10L, 20L, DocumentStatus.COMPLETED);
        document.setContent("document body");
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(knowledgeBase(20L, 1L));

        assertEquals("document body", documentService.getContent(10L));
    }

    @Test
    void getContentRejectsNonOwner() {
        Document document = document(10L, 20L, DocumentStatus.COMPLETED);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(knowledgeBase(20L, 2L));

        assertThrows(BusinessException.class, () -> documentService.getContent(10L));
    }

    @Test
    void parseDocumentDelegatesForOwner() {
        Document document = document(10L, 20L, DocumentStatus.PENDING);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(knowledgeBase(20L, 1L));

        documentService.parseDocument(10L, "ollama");

        verify(vectorizationService).startVectorization(10L, "ollama");
    }

    @Test
    void parseDocumentRejectsNonOwner() {
        Document document = document(10L, 20L, DocumentStatus.PENDING);
        when(documentMapper.selectById(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(knowledgeBase(20L, 2L));

        assertThrows(BusinessException.class, () -> documentService.parseDocument(10L, "ollama"));
        verify(vectorizationService, never()).startVectorization(10L, "ollama");
    }

    @Test
    void restoreRejectsExpiredRecycleEntry() {
        Document document = document(10L, 20L, DocumentStatus.DELETING);
        document.setDeleted(1);
        document.setRecycleExpiresAt(LocalDateTime.now().minusMinutes(1));
        when(documentMapper.selectIncludingDeleted(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(knowledgeBase(20L, 1L));

        assertThrows(BusinessException.class, () -> documentService.restore(10L));
        verify(documentMapper, never()).restoreFromRecycle(10L, DocumentStatus.PENDING.getCode());
    }

    @Test
    void restoreMovesOwnedDocumentBackToPending() {
        Document document = document(10L, 20L, DocumentStatus.DELETING);
        document.setDeleted(1);
        document.setRecycleExpiresAt(LocalDateTime.now().plusDays(1));
        when(documentMapper.selectIncludingDeleted(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectById(20L)).thenReturn(knowledgeBase(20L, 1L));
        when(documentMapper.restoreFromRecycle(10L, DocumentStatus.PENDING.getCode()))
                .thenReturn(1);

        assertDoesNotThrow(() -> documentService.restore(10L));

        verify(documentMapper).restoreFromRecycle(10L, DocumentStatus.PENDING.getCode());
    }

    @Test
    void purgeCreatesOutboxTaskForOwnedRecycleEntry() {
        Document document = document(10L, 20L, DocumentStatus.DELETING);
        document.setDeleted(1);
        when(documentMapper.selectIncludingDeleted(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectIncludingDeleted(20L)).thenReturn(knowledgeBase(20L, 1L));

        documentService.purge(10L);

        verify(deletionService).createTask("DOCUMENT_PURGE", 10L);
    }

    @Test
    void purgeAllowsDocumentUnderDeletedKnowledgeBase() {
        Document document = document(10L, 20L, DocumentStatus.DELETING);
        document.setDeleted(1);
        KnowledgeBase knowledgeBase = knowledgeBase(20L, 1L);
        knowledgeBase.setDeleted(1);
        when(documentMapper.selectIncludingDeleted(10L)).thenReturn(document);
        when(knowledgeBaseMapper.selectIncludingDeleted(20L)).thenReturn(knowledgeBase);

        assertDoesNotThrow(() -> documentService.purge(10L));

        verify(deletionService).createTask("DOCUMENT_PURGE", 10L);
    }

    private Document document(Long id, Long knowledgeBaseId, DocumentStatus status) {
        Document document = new Document();
        document.setId(id);
        document.setKnowledgeBaseId(knowledgeBaseId);
        document.setTitle("Document");
        document.setStatus(status.getCode());
        return document;
    }

    private KnowledgeBase knowledgeBase(Long id, Long userId) {
        KnowledgeBase knowledgeBase = new KnowledgeBase();
        knowledgeBase.setId(id);
        knowledgeBase.setUserId(userId);
        knowledgeBase.setName("Knowledge base");
        knowledgeBase.setStatus(0);
        return knowledgeBase;
    }
}
