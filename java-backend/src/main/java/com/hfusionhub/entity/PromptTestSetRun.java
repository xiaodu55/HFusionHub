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
    private long totalElapsedMs;

    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
