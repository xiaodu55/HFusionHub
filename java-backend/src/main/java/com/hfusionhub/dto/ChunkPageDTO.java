package com.hfusionhub.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import lombok.Builder;
import lombok.Data;

/**
 * 分页分块列表返回。
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@JsonInclude(JsonInclude.Include.NON_NULL)
@Schema(description = "分页分块列表")
public class ChunkPageDTO {

    @Schema(description = "所属文档ID", example = "1")
    private Long documentId;

    @Schema(description = "总块数", example = "42")
    private Long totalChunks;

    @Schema(description = "当前页分块列表")
    private List<ChunkDTO> chunks;
}
