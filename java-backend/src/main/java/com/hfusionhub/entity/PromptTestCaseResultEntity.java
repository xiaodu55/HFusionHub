package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.hfusionhub.handler.JsonMapTypeHandler;
import com.hfusionhub.handler.JsonStringListTypeHandler;
import com.hfusionhub.handler.JsonTypeHandler;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/** Per-case result of a persisted batch run. */
@Data
@TableName(value = "prompt_test_case_result", autoResultMap = true)
public class PromptTestCaseResultEntity {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long runId;
    private Long caseId;
    private String question;
    private String renderedTemplate;
    private String content;
    private String model;
    private int tokenCount;

    @TableField(typeHandler = JsonMapTypeHandler.class)
    private Map<String, Object> tokenUsage;

    @TableField(typeHandler = JsonTypeHandler.class)
    private List<Map<String, Object>> sources;

    private long elapsedMs;
    private boolean success;
    private boolean passed;
    private String error;

    /** Reasons for failing pass rules, e.g. ["缺少关键词: 退款", "未引用文档: 12"]. */
    @TableField(typeHandler = JsonStringListTypeHandler.class)
    private List<String> passNotes;

    private LocalDateTime createdAt;
}
