package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.Map;
import lombok.Data;

/**
 * 开放 API 废标自检响应（/openapi/bid/check，P2-7）
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "开放 API 废标自检响应")
public class OpenApiBidCheckResponse {

    @Schema(description = "状态：ok | error")
    private String status;

    @Schema(description = "投标项目 ID")
    private Long projectId;

    @Schema(description = "自检统计 {total, critical, warning, info}")
    private Map<String, Object> summary;

    @Schema(description = "提示信息（error 时非空）")
    private String message;
}
