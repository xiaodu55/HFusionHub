package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.entity.*;
import com.hfusionhub.enums.DocumentStatus;
import com.hfusionhub.mapper.*;
import com.hfusionhub.service.DeletionService;
import com.hfusionhub.service.VectorizationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.File;
import java.time.LocalDateTime;
import java.util.List;

/**
 * 异步删除任务服务实现 — 支持步骤化级联删除、失败重试
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class DeletionServiceImpl implements DeletionService {

    private final DeletionTaskMapper deletionTaskMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final DocumentMapper documentMapper;
    private final DocumentChunkMapper documentChunkMapper;
    private final DocumentIndexJobMapper documentIndexJobMapper;
    private final ConversationMapper conversationMapper;
    private final MessageMapper messageMapper;
    private final VectorizationService vectorizationService;

    private static final int DEFAULT_MAX_RETRIES = 5;
    private static final int TASK_BATCH_SIZE = 10;

    @Override
    @Transactional
    public DeletionTask createTask(String taskType, Long targetId) {
        DeletionTask task = new DeletionTask();
        task.setTaskType(taskType);
        task.setTargetId(targetId);
        task.setStatus("PENDING");
        task.setStepIndex(0);
        task.setMaxRetries(DEFAULT_MAX_RETRIES);
        task.setRetryCount(0);
        deletionTaskMapper.insert(task);
        log.info("删除任务已创建: type={}, targetId={}, taskId={}", taskType, targetId, task.getId());
        return task;
    }

    @Override
    public List<DeletionTask> getPendingTasks() {
        return deletionTaskMapper.selectPendingTasks(TASK_BATCH_SIZE);
    }

    @Override
    @Transactional
    public void markFailed(DeletionTask task, String errorMessage) {
        task.setRetryCount(task.getRetryCount() + 1);
        task.setErrorMessage(errorMessage);
        if (task.getRetryCount() >= task.getMaxRetries()) {
            task.setStatus("FAILED");
            log.error("删除任务耗尽重试次数: taskId={}, targetId={}", task.getId(), task.getTargetId());
            markDocumentDeleteFailed(task, errorMessage);
        } else {
            task.setStatus("RETRYING");
            log.warn("删除任务将重试: taskId={}, retryCount={}/{}", task.getId(), task.getRetryCount(), task.getMaxRetries());
        }
        deletionTaskMapper.updateById(task);
    }

    @Override
    @Transactional
    public void executeStep(DeletionTask task) {
        task.setStatus("PROCESSING");
        deletionTaskMapper.updateById(task);

        try {
            if ("KB_DELETE".equals(task.getTaskType())) {
                executeKbDeleteStep(task);
            } else if ("DOCUMENT_DELETE".equals(task.getTaskType())) {
                executeDocumentDeleteStep(task);
            }
        } catch (Exception e) {
            log.error("删除任务执行失败: taskId={}, step={}", task.getId(), task.getStepIndex(), e);
            markFailed(task, truncate(e.getMessage(), 2000));
        }
    }

    // ──────────────── KB 删除级联步骤 ────────────────

    private void executeKbDeleteStep(DeletionTask task) {
        KnowledgeBase kb = knowledgeBaseMapper.selectById(task.getTargetId());
        if (kb == null) {
            task.setStatus("COMPLETED");
            task.setStep("KB_NOT_FOUND");
            deletionTaskMapper.updateById(task);
            return;
        }

        switch (task.getStepIndex()) {
            case 0 -> markKbDeleting(kb, task);
            case 1 -> deleteKbVectors(kb, task);
            case 2 -> deleteKbChunkMetadata(kb, task);
            case 3 -> deleteKbIndexJobs(kb, task);
            case 4 -> deleteKbDiskFiles(kb, task);
            case 5 -> logicalDeleteKbDocuments(kb, task);
            case 6 -> logicalDeleteKbConversations(kb, task);
            case 7 -> logicalDeleteKnowledgeBase(kb, task);
            case 8 -> completeTask(task);
            default -> throw new BusinessException("未知删除步骤: " + task.getStepIndex());
        }
    }

    private void markKbDeleting(KnowledgeBase kb, DeletionTask task) {
        kb.setStatus(CommonConstants.KB_STATUS_DELETING);
        knowledgeBaseMapper.updateById(kb);
        advanceStep(task, "KB_MARKED_DELETING");
    }

    private void deleteKbVectors(KnowledgeBase kb, DeletionTask task) {
        List<Document> docs = getKbDocuments(kb.getId());
        for (Document doc : docs) {
            try {
                vectorizationService.deleteDocumentIndex(doc.getId());
            } catch (Exception e) {
                log.warn("向量删除失败(将继续): documentId={}, error={}", doc.getId(), e.getMessage());
                // 不中断：向量可由定时清理任务处理
            }
        }
        advanceStep(task, "VECTORS_DELETED");
    }

    private void deleteKbChunkMetadata(KnowledgeBase kb, DeletionTask task) {
        List<Document> docs = getKbDocuments(kb.getId());
        for (Document doc : docs) {
            documentChunkMapper.deleteByDocumentId(doc.getId());
        }
        advanceStep(task, "CHUNKS_DELETED");
    }

    private void deleteKbIndexJobs(KnowledgeBase kb, DeletionTask task) {
        List<Document> docs = getKbDocuments(kb.getId());
        for (Document doc : docs) {
            documentIndexJobMapper.delete(new LambdaQueryWrapper<DocumentIndexJob>()
                    .eq(DocumentIndexJob::getDocumentId, doc.getId()));
        }
        advanceStep(task, "INDEX_JOBS_DELETED");
    }

    private void deleteKbDiskFiles(KnowledgeBase kb, DeletionTask task) {
        List<Document> docs = getKbDocuments(kb.getId());
        for (Document doc : docs) {
            if (doc.getFilePath() != null) {
                File file = new File(doc.getFilePath());
                if (file.exists() && !file.delete()) {
                    log.warn("磁盘文件删除失败: {}", doc.getFilePath());
                }
            }
        }
        advanceStep(task, "DISK_FILES_DELETED");
    }

    private void logicalDeleteKbDocuments(KnowledgeBase kb, DeletionTask task) {
        List<Document> docs = getKbDocuments(kb.getId());
        for (Document doc : docs) {
            documentMapper.deleteById(doc.getId());
        }
        advanceStep(task, "DOCUMENTS_DELETED");
    }

    private void logicalDeleteKbConversations(KnowledgeBase kb, DeletionTask task) {
        LambdaQueryWrapper<Conversation> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Conversation::getKnowledgeBaseId, kb.getId());
        List<Conversation> conversations = conversationMapper.selectList(wrapper);
        for (Conversation conv : conversations) {
            // 物理删除消息
            messageMapper.delete(new LambdaQueryWrapper<Message>()
                    .eq(Message::getConversationId, conv.getId()));
            // 逻辑删除会话
            conversationMapper.deleteById(conv.getId());
        }
        advanceStep(task, "CONVERSATIONS_DELETED");
    }

    private void logicalDeleteKnowledgeBase(KnowledgeBase kb, DeletionTask task) {
        knowledgeBaseMapper.deleteById(kb.getId());
        advanceStep(task, "KB_DELETED");
    }

    // ──────────────── 文档删除步骤 ────────────────

    private void executeDocumentDeleteStep(DeletionTask task) {
        Document doc = documentMapper.selectById(task.getTargetId());
        if (doc == null) {
            task.setStatus("COMPLETED");
            task.setStep("DOC_NOT_FOUND");
            deletionTaskMapper.updateById(task);
            return;
        }

        switch (task.getStepIndex()) {
            case 0 -> {
                try {
                    vectorizationService.deleteDocumentIndex(doc.getId());
                } catch (Exception e) {
                    log.warn("文档向量删除失败: documentId={}", doc.getId(), e);
                }
                advanceStep(task, "VECTORS_DELETED");
            }
            case 1 -> {
                documentChunkMapper.deleteByDocumentId(doc.getId());
                advanceStep(task, "CHUNKS_DELETED");
            }
            case 2 -> {
                documentIndexJobMapper.delete(new LambdaQueryWrapper<DocumentIndexJob>()
                        .eq(DocumentIndexJob::getDocumentId, doc.getId()));
                advanceStep(task, "INDEX_JOBS_DELETED");
            }
            case 3 -> {
                if (doc.getFilePath() != null) {
                    File file = new File(doc.getFilePath());
                    if (file.exists()) file.delete();
                }
                advanceStep(task, "DISK_FILE_DELETED");
            }
            case 4 -> {
                documentMapper.deleteById(doc.getId());
                advanceStep(task, "DOCUMENT_DELETED");
            }
            case 5 -> completeTask(task);
            default -> throw new BusinessException("未知删除步骤: " + task.getStepIndex());
        }
    }

    // ──────────────── 辅助方法 ────────────────

    private List<Document> getKbDocuments(Long kbId) {
        LambdaQueryWrapper<Document> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(Document::getKnowledgeBaseId, kbId);
        return documentMapper.selectList(wrapper);
    }

    private void advanceStep(DeletionTask task, String stepName) {
        task.setStep(stepName);
        task.setStepIndex(task.getStepIndex() + 1);
        task.setStatus("PENDING");
        deletionTaskMapper.updateById(task);
    }

    private void completeTask(DeletionTask task) {
        task.setStatus("COMPLETED");
        task.setStep("COMPLETED");
        task.setErrorMessage(null);
        deletionTaskMapper.updateById(task);
        log.info("删除任务完成: taskId={}, type={}, targetId={}", task.getId(), task.getTaskType(), task.getTargetId());
    }

    private String truncate(String value, int maxLength) {
        if (value == null) return null;
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
    }

    private void markDocumentDeleteFailed(DeletionTask task, String errorMessage) {
        if (!"DOCUMENT_DELETE".equals(task.getTaskType())) {
            return;
        }
        Document doc = documentMapper.selectById(task.getTargetId());
        if (doc == null) {
            return;
        }
        doc.setStatus(DocumentStatus.DELETE_FAILED.getCode());
        doc.setErrorMessage(truncate(errorMessage, 1000));
        documentMapper.updateById(doc);
    }
}
