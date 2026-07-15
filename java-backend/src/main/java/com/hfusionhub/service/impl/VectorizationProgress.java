package com.hfusionhub.service.impl;

import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.DocumentIndexJob;
import com.hfusionhub.enums.DocumentStatus;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Map;

/**
 * 向量化进度估算与状态展示的纯计算族(自 VectorizationServiceImpl 收口)。
 *
 * <p>全部为无状态静态方法:输入 document/job/状态,输出展示字段。
 * 不做任何 I/O —— 与 Python 任务状态的 HTTP 合并(mergePythonTaskStatus)
 * 留在 VectorizationServiceImpl。</p>
 *
 * @author HFusionHub Team
 */
final class VectorizationProgress {

    private VectorizationProgress() {
    }

    static String statusName(Integer statusCode) {
        DocumentStatus status = DocumentStatus.fromCode(statusCode);
        return status == null ? "PENDING" : status.name();
    }

    static void enrichWithEstimatedProgress(
            Map<String, Object> response, Document document, DocumentIndexJob job, String status) {
        int initialEstimatedSeconds = estimateProcessingSeconds(document);
        int elapsedSeconds = elapsedSeconds(job);
        int progress = estimateProgress(status, elapsedSeconds, initialEstimatedSeconds);
        int estimatedSeconds = dynamicEstimatedSeconds(status, elapsedSeconds, progress, initialEstimatedSeconds);
        int remainingSeconds = isTerminalStatus(status) ? 0 : Math.max(1, estimatedSeconds - elapsedSeconds);

        response.put("stage", stageForStatus(status, progress));
        response.put("progress", progress);
        response.put("elapsed_seconds", elapsedSeconds);
        response.put("estimated_seconds", estimatedSeconds);
        response.put("initial_estimated_seconds", initialEstimatedSeconds);
        response.put("remaining_seconds", remainingSeconds);
    }

    static void copyIfPresent(Map<String, Object> target, Map<String, Object> source, String key) {
        if (source.containsKey(key) && source.get(key) != null) {
            target.put(key, source.get(key));
        }
    }

    static int estimateProcessingSeconds(Document document) {
        long fileSize = document.getFileSize() == null ? 1024 * 1024 : document.getFileSize();
        long sizeMb = Math.max(1, (long) Math.ceil(fileSize / (1024.0 * 1024.0)));
        String fileType =
                document.getFileType() == null ? "" : document.getFileType().toLowerCase();
        int base =
                switch (fileType) {
                    case "pdf", ".pdf" -> 45;
                    case "docx", ".docx" -> 35;
                    case "txt", ".txt", "md", ".md" -> 15;
                    default -> 30;
                };
        long estimate = base + sizeMb * 25;
        return (int) Math.max(15, Math.min(900, estimate));
    }

    static int elapsedSeconds(DocumentIndexJob job) {
        if (job == null || job.getStartedAt() == null) {
            return 0;
        }
        LocalDateTime end = job.getCompletedAt() == null ? LocalDateTime.now() : job.getCompletedAt();
        return (int) Math.max(0, Duration.between(job.getStartedAt(), end).toSeconds());
    }

    static int estimateProgress(String status, int elapsedSeconds, int estimatedSeconds) {
        if ("COMPLETED".equals(status)) {
            return 100;
        }
        if ("FAILED".equals(status) || "ERROR".equals(status)) {
            return 100;
        }
        if (!"PROCESSING".equals(status)) {
            return 0;
        }
        if (estimatedSeconds <= 0) {
            return 10;
        }
        int progress = 5 + (int) Math.floor((elapsedSeconds / (double) estimatedSeconds) * 80);
        return Math.max(5, Math.min(90, progress));
    }

    static int dynamicEstimatedSeconds(String status, int elapsedSeconds, int progress, int initialEstimatedSeconds) {
        if (isTerminalStatus(status) || progress <= 5 || elapsedSeconds < 1) {
            return initialEstimatedSeconds;
        }

        double observedTotal = elapsedSeconds * 100.0 / Math.min(progress, 99);
        double dynamicTotal = Math.max(initialEstimatedSeconds * 0.75, observedTotal);
        return (int) Math.max(15, Math.min(900, Math.round(dynamicTotal)));
    }

    static String stageForStatus(String status, int progress) {
        if ("COMPLETED".equals(status)) {
            return "completed";
        }
        if ("FAILED".equals(status) || "ERROR".equals(status)) {
            return "failed";
        }
        if (!"PROCESSING".equals(status)) {
            return "queued";
        }
        if (progress < 25) {
            return "parsing";
        }
        if (progress < 40) {
            return "chunking";
        }
        if (progress < 90) {
            return "embedding";
        }
        return "storing";
    }

    static boolean isTerminalStatus(String status) {
        return "COMPLETED".equals(status) || "FAILED".equals(status) || "ERROR".equals(status);
    }
}
