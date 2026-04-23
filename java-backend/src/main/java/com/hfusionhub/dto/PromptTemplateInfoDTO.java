package com.hfusionhub.dto;

import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Data;

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
    private LocalDateTime recycledAt;
    private LocalDateTime recycleExpiresAt;
}
