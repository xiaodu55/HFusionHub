package com.hfusionhub.dto;

import com.hfusionhub.common.dto.PageQuery;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
@Schema(description = "RAG intent node query")
public class RagIntentNodeQueryDTO extends PageQuery {

    private Long parentId;
    private String keyword;
    private String level;
    private String kind;
    private Integer enabled;
}
