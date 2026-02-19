package com.hfusionhub.scheduler;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.entity.Document;
import com.hfusionhub.mapper.DocumentMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.io.File;
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 孤儿数据清理调度器 — 定期清理孤儿磁盘文件、临时文件
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class OrphanCleanupScheduler {

    private final DocumentMapper documentMapper;

    private static final String UPLOAD_DIR = "uploads/documents";
    private static final String TEMP_SUBDIR = "temp";
    private static final long TEMP_FILE_MAX_AGE_HOURS = 1;

    /**
     * 每小时执行一次孤儿文件清理
     */
    @Scheduled(fixedDelay = 3_600_000)
    public void cleanupOrphanFiles() {
        String userDir = System.getProperty("user.dir");
        Path uploadPath = Paths.get(userDir, UPLOAD_DIR);

        if (!Files.exists(uploadPath)) return;

        // 1. 获取数据库中所有非删除文档的 filePath 集合
        List<Document> allDocs = documentMapper.selectList(new LambdaQueryWrapper<>());
        Set<String> knownPaths = allDocs.stream()
                .map(Document::getFilePath)
                .filter(p -> p != null && !p.isBlank())
                .map(p -> Path.of(p).getFileName().toString())
                .collect(Collectors.toSet());

        // 2. 扫描正式目录中的孤儿文件
        File dir = uploadPath.toFile();
        File[] files = dir.listFiles(File::isFile);
        if (files != null) {
            for (File file : files) {
                if (!knownPaths.contains(file.getName())) {
                    if (file.delete()) {
                        log.info("已清理孤儿文件: {}", file.getName());
                    } else {
                        log.warn("清理孤儿文件失败: {}", file.getName());
                    }
                }
            }
        }

        // 3. 清理 temp 目录中超时的文件
        Path tempPath = uploadPath.resolve(TEMP_SUBDIR);
        if (Files.exists(tempPath)) {
            Instant cutoff = Instant.now().minus(TEMP_FILE_MAX_AGE_HOURS, ChronoUnit.HOURS);
            File tempDir = tempPath.toFile();
            File[] tempFiles = tempDir.listFiles();
            if (tempFiles != null) {
                for (File file : tempFiles) {
                    try {
                        if (file.toPath().toFile().lastModified() < cutoff.toEpochMilli()) {
                            if (file.delete()) {
                                log.debug("已清理超时临时文件: {}", file.getName());
                            }
                        }
                    } catch (Exception e) {
                        log.warn("清理临时文件异常: {}", file.getName(), e);
                    }
                }
            }
        }
    }

    /**
     * 每10分钟重试可重试的删除任务（定时补偿）
     * 注意：DeletionTaskScheduler 已每30秒处理待处理任务，此处处理长时间 FAILED 的重试
     */
    @Scheduled(fixedDelay = 600_000)
    public void retryLongFailedDeletionTasks() {
        // 重试逻辑已由 DeletionTaskScheduler + DeletionService.markFailed 的 RETRYING 状态覆盖
        // 此方法保留用于未来扩展：如超长时间 FAILED 任务的人工介入告警
    }
}
