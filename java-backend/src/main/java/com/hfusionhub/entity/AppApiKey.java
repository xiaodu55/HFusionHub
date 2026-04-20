package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 应用 API Key（仅存 SHA-256 哈希，不存明文）
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("app_api_key")
@Schema(description = "应用 API Key")
public class AppApiKey extends BaseEntity {

    @TableId(type = IdType.AUTO)
    @Schema(description = "Key ID")
    private Long id;

    @Schema(description = "FK → app.id")
    private Long appId;

    @Schema(description = "Key 名称")
    private String name;

    @Schema(description = "密钥 SHA-256 hex")
    private String keyHash;

    @Schema(description = "明文前缀前 8 位（展示用）")
    private String keyPrefix;

    @Schema(description = "1 启用, 0 停用")
    private Integer enabled;
}
