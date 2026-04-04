package com.hfusionhub.scheduler;

import com.hfusionhub.entity.Document;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.service.DeletionService;
import com.hfusionhub.tenant.TenantContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * Schedules physical cleanup for documents whose seven-day recycle period
 * has expired.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class RecycleBinCleanupScheduler {

    private final DocumentMapper documentMapper;
    private final DeletionService deletionService;

    @Scheduled(fixedDelayString = "${document.recycle.cleanup-delay-ms:3600000}")
    public void scheduleExpiredDocuments() {
        TenantContext.runAsSystem(() -> {
            List<Document> expired = documentMapper.selectExpiredRecycled(100);
            for (Document document : expired) {
                try {
                    deletionService.createTask("DOCUMENT_PURGE", document.getId());
                } catch (Exception e) {
                    log.warn("创建回收站过期清理任务失败: documentId={}", document.getId(), e);
                }
            }
        });
    }
}
