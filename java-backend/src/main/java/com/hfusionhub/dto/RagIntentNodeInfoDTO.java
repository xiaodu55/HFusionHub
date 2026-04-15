package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

@Data
@Builder
@Schema(description = "RAG intent node info")
public class RagIntentNodeInfoDTO {

    private Long id;
    private Long userId;
    private Long parentId;
    private String intentCode;
    private String name;
    private String description;
    private String level;
    private String kind;
    private Long knowledgeBaseId;
    private String knowledgeBaseName;
    private Long mcpToolId;
    private Integer topK;
    private String routeConfig;
    private Integer enabled;
    private Integer sortOrder;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    @Builder.Default
    private List<RagIntentNodeInfoDTO> children = new ArrayList<>();
}
