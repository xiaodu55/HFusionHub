package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
@Schema(description = "Update RAG intent node request")
public class RagIntentNodeUpdateDTO {

    private Long parentId;

    @Pattern(
            regexp = "^[A-Za-z0-9_.:-]{2,64}$",
            message = "intentCode only supports letters, numbers, dot, colon, dash and underscore")
    private String intentCode;

    @Size(max = 100, message = "name must be at most 100 characters")
    private String name;

    @Size(max = 500, message = "description must be at most 500 characters")
    private String description;

    @Pattern(regexp = "^(DOMAIN|CATEGORY|TOPIC)$", message = "level must be DOMAIN, CATEGORY or TOPIC")
    private String level;

    @Pattern(regexp = "^(KB|SYSTEM|MCP)$", message = "kind must be KB, SYSTEM or MCP")
    private String kind;

    private Long knowledgeBaseId;

    private Long mcpToolId;

    @Min(value = 1, message = "topK must be at least 1")
    @Max(value = 20, message = "topK must be at most 20")
    private Integer topK;

    @Size(max = 4000, message = "routeConfig must be at most 4000 characters")
    private String routeConfig;

    @Min(value = 0, message = "enabled must be 0 or 1")
    @Max(value = 1, message = "enabled must be 0 or 1")
    private Integer enabled;

    private Integer sortOrder;
}
