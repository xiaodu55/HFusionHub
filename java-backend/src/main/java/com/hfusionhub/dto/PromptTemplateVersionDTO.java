package com.hfusionhub.dto;

import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

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
