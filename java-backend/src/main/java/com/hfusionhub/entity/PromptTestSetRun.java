package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/** A persisted batch run of a prompt test set (snapshots template + KB used). */
@Data
@TableName("prompt_test_set_run")
public class PromptTestSetRun {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long setId;
    private Long userId;

    /** Template snapshot (optional — null for ad-hoc templates). */
    private Long templateId;
    private Integer templateVersion;
    private String templateName;
    private String templateContent;

    private Long knowledgeBaseId;

    private int totalCases;
    private int successCount;
    private int failureCount;
    private int passCount;
    private long totalElapsedMs;

    /** pending|running|succeeded|failed|cancelled */
    private String status;

    /** 重试次数（每次 retry 递增） */
    private int attemptNumber;

    /** 已完成用例数（用于实时进度） */
    private int progressCount;

    /** 终态失败原因（供前端展示） */
    private String errorMessage;

    private LocalDateTime scheduledAt;
    private LocalDateTime startedAt;
    private LocalDateTime completedAt;

    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
