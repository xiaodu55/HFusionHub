package com.hfusionhub.dto;

import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class PromptTemplateVersionDTO {
    private Long id;
    private Integer version;
    private String name;
    private String description;
    private String content;
    private String status;
    private String operation;
    private Long operatorId;
    private LocalDateTime createdAt;
}
