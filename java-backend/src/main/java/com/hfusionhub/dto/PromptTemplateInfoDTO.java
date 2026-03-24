package com.hfusionhub.dto;

import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@Builder
public class PromptTemplateInfoDTO {
    private Long id;
    private String name;
    private String description;
    private String content;
    private String status;
    private Integer version;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
