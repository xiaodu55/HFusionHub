package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;

/**
 * 演示知识库导入结果
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "演示知识库导入结果")
public class DemoImportResultDTO {

    @Schema(description = "演示知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "演示知识库名称")
    private String knowledgeBaseName;

    @Schema(description = "新导入并触发解析的文档数")
    private int importedCount;

    @Schema(description = "已存在而跳过的文档数")
    private int skippedCount;

    @Schema(description = "触发解析失败的文档数（AI 服务不可用时，可在文档页稍后重试）")
    private int parseFailedCount;

    @Schema(description = "提示信息")
    private String message;
}
