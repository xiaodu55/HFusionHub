package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.hfusionhub.handler.JsonLongListTypeHandler;
import com.hfusionhub.handler.JsonMapTypeHandler;
import com.hfusionhub.handler.JsonStringListTypeHandler;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import lombok.Data;

/** A single fixed question (+ optional variable values) inside a prompt test set. */
@Data
@TableName(value = "prompt_test_case", autoResultMap = true)
public class PromptTestCase {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long setId;
    private String question;

    /** Template variables, e.g. {"role":"专家","topic":"RAG"} — substituted into {{var}} in the template. */
    @TableField(typeHandler = JsonMapTypeHandler.class)
    private Map<String, Object> variables;

    /** Expected keywords — every keyword must appear in the AI answer (case-insensitive). */
    @TableField(typeHandler = JsonStringListTypeHandler.class)
    private List<String> expectedKeywords;

    /** Required document ids — every doc must be cited in the answer sources. */
    @TableField(typeHandler = JsonLongListTypeHandler.class)
    private List<Long> requiredDocumentIds;

    private Integer sortOrder;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;
}
