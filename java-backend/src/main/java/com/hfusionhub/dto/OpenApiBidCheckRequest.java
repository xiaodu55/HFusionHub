package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 开放 API 废标自检请求（/openapi/bid/check，P2-7）
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "开放 API 废标自检请求")
public class OpenApiBidCheckRequest {

    @Schema(description = "投标项目 ID（须属于 API Key 所属租户）")
    private Long projectId;
}
