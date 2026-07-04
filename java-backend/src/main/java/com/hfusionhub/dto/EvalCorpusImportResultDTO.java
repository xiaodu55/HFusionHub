package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.util.Map;

/**
 * 评测语料导入结果
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "评测语料导入结果")
public class EvalCorpusImportResultDTO {

    @Schema(description = "评测知识库ID")
    private Long knowledgeBaseId;

    @Schema(description = "评测知识库名称")
    private String knowledgeBaseName;

    @Schema(description = "新导入并触发解析的文档数")
    private int importedCount;

    @Schema(description = "已存在而跳过的文档数")
    private int skippedCount;

    @Schema(description = "触发解析失败的文档数（AI 服务不可用时，可在文档页稍后重试）")
    private int parseFailedCount;

    @Schema(description = "业务码 → 文档ID 映射（评测集 expected_doc_ids 到系统文档 ID 的翻译依据）")
    private Map<String, String> docIdMap;
}
