package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.Map;
import lombok.Builder;
import lombok.Data;

/** 单个用例的批量运行结果 */
@Data
@Builder
@Schema(description = "单个用例的批量运行结果")
public class PromptTestCaseResult {

    @Schema(description = "用例 ID")
    private Long caseId;

    @Schema(description = "用例问题")
    private String question;

    @Schema(description = "最终传入模板（变量替换后）")
    private String renderedTemplate;

    @Schema(description = "AI 回答内容（Markdown），失败时为 null")
    private String content;

    @Schema(description = "使用的模型名称")
    private String model;

    @Schema(description = "总 token 消耗")
    private int tokenCount;

    @Schema(description = "详细 token 用量")
    private Map<String, Object> tokenUsage;

    @Schema(description = "引用来源列表")
    private List<Map<String, Object>> sources;

    @Schema(description = "服务端耗时（毫秒）")
    private long elapsedMs;

    @Schema(description = "是否成功")
    private boolean success;

    @Schema(description = "是否通过（成功且满足全部通过规则；未配置规则时等于 success）")
    private boolean passed;

    @Schema(description = "未通过原因，如 [\"缺少关键词: 退款\"]")
    private List<String> passNotes;

    @Schema(description = "失败时的错误信息")
    private String error;
}
