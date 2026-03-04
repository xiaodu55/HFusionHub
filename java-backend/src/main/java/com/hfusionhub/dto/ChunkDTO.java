package com.hfusionhub.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

import java.util.List;
import java.util.Map;

/**
 * 文档分块详情返回。
 *
 * <p>与 {@link com.hfusionhub.entity.DocumentChunk} 解耦，
 * 避免实体字段变更影响 API 契约。</p>
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@JsonInclude(JsonInclude.Include.NON_NULL)
@Schema(description = "文档分块详情")
public class ChunkDTO {

    @Schema(description = "分块唯一标识", example = "chunk_a1b2c3d4")
    private String chunkId;

    @Schema(description = "所属文档ID", example = "1")
    private Long documentId;

    @Schema(description = "在文档中的序号（从0开始）", example = "0")
    private Integer index;

    @Schema(description = "分块文本内容（可能为摘要，完整内容从向量库获取）")
    private String content;

    @Schema(description = "块类型", example = "text")
    private String blockType;

    @Schema(description = "层级路径", example = "[\"第一章\",\"第一节\"]")
    private List<String> outlinePath;

    @Schema(description = "扩展元数据")
    private Map<String, Object> metadata;
}
