package com.hfusionhub.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 应用 API Key 信息
 *
 * @author HFusionHub Team
 */
@Data
@Schema(description = "应用 API Key 信息")
public class AppApiKeyInfoDTO {

    @Schema(description = "Key ID")
    private Long id;

    @Schema(description = "应用ID")
    private Long appId;

    @Schema(description = "Key 名称")
    private String name;

    @Schema(description = "明文前缀前 8 位（展示用）")
    private String keyPrefix;

    @Schema(description = "完整密钥明文（仅创建时返回一次，列表接口为 null）")
    private String secret;

    @Schema(description = "1 启用, 0 停用")
    private Integer enabled;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
