package com.hfusionhub.service.impl;

import static org.assertj.core.api.Assertions.assertThat;

import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.DocumentIndexJob;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * VectorizationProgress 单元测试 — 进度估算/阶段映射纯计算族
 * (自 VectorizationServiceImpl 收口后的行为锁定)。
 */
class VectorizationProgressTest {

    private Document document(long sizeBytes, String fileType) {
        Document d = new Document();
        d.setFileSize(sizeBytes);
        d.setFileType(fileType);
        return d;
    }

    @Test
    void estimateProcessingSecondsClampsToBounds() {
        // 1MB PDF: base 45 + 1*25 = 70
        assertThat(VectorizationProgress.estimateProcessingSeconds(document(1024 * 1024, "pdf"))).isEqualTo(70);
        // 超大文件封顶 900
        assertThat(VectorizationProgress.estimateProcessingSeconds(document(500L * 1024 * 1024, "pdf")))
                .isEqualTo(900);
        // 未知类型按 30 起步;sizeMb 下限为 1(30+25=55)
        assertThat(VectorizationProgress.estimateProcessingSeconds(document(1024, "xyz"))).isEqualTo(55);
        // txt 15+25=40(下限 15 为防御性钳制)
        assertThat(VectorizationProgress.estimateProcessingSeconds(document(0, "txt"))).isEqualTo(40);
    }

    @Test
    void estimateProgressBoundaries() {
        assertThat(VectorizationProgress.estimateProgress("COMPLETED", 10, 100)).isEqualTo(100);
        assertThat(VectorizationProgress.estimateProgress("FAILED", 10, 100)).isEqualTo(100);
        assertThat(VectorizationProgress.estimateProgress("PENDING", 10, 100)).isZero();
        // PROCESSING: 5% 起步、90% 封顶
        assertThat(VectorizationProgress.estimateProgress("PROCESSING", 0, 100)).isEqualTo(5);
        assertThat(VectorizationProgress.estimateProgress("PROCESSING", 100000, 100)).isEqualTo(90);
    }

    @Test
    void stageForStatusTransitions() {
        assertThat(VectorizationProgress.stageForStatus("COMPLETED", 100)).isEqualTo("completed");
        assertThat(VectorizationProgress.stageForStatus("FAILED", 100)).isEqualTo("failed");
        assertThat(VectorizationProgress.stageForStatus("PENDING", 0)).isEqualTo("queued");
        assertThat(VectorizationProgress.stageForStatus("PROCESSING", 10)).isEqualTo("parsing");
        assertThat(VectorizationProgress.stageForStatus("PROCESSING", 30)).isEqualTo("chunking");
        assertThat(VectorizationProgress.stageForStatus("PROCESSING", 50)).isEqualTo("embedding");
        assertThat(VectorizationProgress.stageForStatus("PROCESSING", 95)).isEqualTo("storing");
    }

    @Test
    void dynamicEstimatedSecondsStaysWithinBounds() {
        // 终态/低进度/零耗时 → 回落初始估算
        assertThat(VectorizationProgress.dynamicEstimatedSeconds("COMPLETED", 60, 100, 100)).isEqualTo(100);
        assertThat(VectorizationProgress.dynamicEstimatedSeconds("PROCESSING", 60, 5, 100)).isEqualTo(100);
        assertThat(VectorizationProgress.dynamicEstimatedSeconds("PROCESSING", 0, 50, 100)).isEqualTo(100);
        // 观测外推:60s 走到 50% → 观测总时长 120s(>75% 初始)→ 动态估算 120
        assertThat(VectorizationProgress.dynamicEstimatedSeconds("PROCESSING", 60, 50, 100)).isEqualTo(120);
        // 封顶 900
        assertThat(VectorizationProgress.dynamicEstimatedSeconds("PROCESSING", 6000, 90, 100)).isEqualTo(900);
    }

    @Test
    void elapsedSecondsUsesCompletedAtWhenPresent() {
        DocumentIndexJob job = new DocumentIndexJob();
        job.setStartedAt(LocalDateTime.now().minusSeconds(30));
        int running = VectorizationProgress.elapsedSeconds(job);
        assertThat(running).isBetween(25, 40);

        job.setCompletedAt(job.getStartedAt().plusSeconds(120));
        assertThat(VectorizationProgress.elapsedSeconds(job)).isEqualTo(120);
    }

    @Test
    void elapsedSecondsZeroWithoutStartedAt() {
        assertThat(VectorizationProgress.elapsedSeconds(null)).isZero();
        assertThat(VectorizationProgress.elapsedSeconds(new DocumentIndexJob())).isZero();
    }

    @Test
    void copyIfPresentSkipsMissingAndNull() {
        Map<String, Object> target = new HashMap<>();
        Map<String, Object> source = new HashMap<>();
        source.put("progress", 42);
        source.put("empty", null);

        VectorizationProgress.copyIfPresent(target, source, "progress");
        VectorizationProgress.copyIfPresent(target, source, "missing");
        VectorizationProgress.copyIfPresent(target, source, "empty");

        assertThat(target).containsEntry("progress", 42).hasSize(1);
    }

    @Test
    void enrichPopulatesAllDisplayFields() {
        Map<String, Object> response = new HashMap<>();
        Document doc = document(1024 * 1024, "pdf");
        DocumentIndexJob job = new DocumentIndexJob();
        job.setStartedAt(LocalDateTime.now().minusSeconds(10));

        VectorizationProgress.enrichWithEstimatedProgress(response, doc, job, "PROCESSING");

        assertThat(response).containsKeys("stage", "progress", "elapsed_seconds",
                "estimated_seconds", "initial_estimated_seconds", "remaining_seconds");
        assertThat(response.get("stage")).isEqualTo("parsing");
    }

    @Test
    void statusNameFallsBackToPendingForUnknownCode() {
        assertThat(VectorizationProgress.statusName(null)).isEqualTo("PENDING");
    }
}
