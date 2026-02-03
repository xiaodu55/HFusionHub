package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 文档名称返回DTO
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "文档名称返回")
public class DocumentNameDTO {

    @Schema(description = "文档ID")
    private Long id;

    @Schema(description = "文档名称")
    private String name;
}
