package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import lombok.Builder;
import lombok.Data;

/**
 * 演示数据导入结果
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "演示数据导入结果")
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

    @Schema(description = "其他菜单的分项导入结果（回答方案/笔记/记忆/应用/公告）")
    private List<SectionResult> sections;

    @Schema(description = "提示信息")
    private String message;

    /**
     * 单个菜单（分节）的导入结果
     */
    @Data
    @Builder
    @Schema(description = "分项导入结果")
    public static class SectionResult {

        @Schema(description = "分节标识: prompts|notes|memory|apps|notices")
        private String section;

        @Schema(description = "菜单显示名，如「回答方案」")
        private String label;

        @Schema(description = "新导入条数")
        private int importedCount;

        @Schema(description = "已存在跳过条数")
        private int skippedCount;
    }
}
