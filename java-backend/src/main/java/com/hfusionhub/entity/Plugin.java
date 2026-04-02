package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

/**
 * 工具插件实体
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("plugin")
@Schema(description = "工具插件")
public class Plugin extends BaseEntity {

    @TableId(type = IdType.AUTO)
    @Schema(description = "插件数据库ID")
    private Long id;

    @Schema(description = "插件UUID")
    private String pluginId;

    @Schema(description = "机器名: github_connector")
    private String name;

    @Schema(description = "显示名称")
    private String displayName;

    @Schema(description = "插件描述")
    private String description;

    @Schema(description = "语义化版本 semver")
    private String version;

    @Schema(description = "作者")
    private String author;

    @Schema(description = "作者邮箱")
    private String authorEmail;

    @Schema(description = "许可证")
    private String license;

    @Schema(description = "最低 HFusionHub 版本")
    private String minHfusionhubVersion;

    @Schema(description = "最高 HFusionHub 版本")
    private String maxHfusionhubVersion;

    @Schema(description = "图标 URL")
    private String iconUrl;

    @Schema(description = "来源: local|git|wheel")
    private String source;

    @Schema(description = "状态: active|disabled|failed|pending")
    private String status;

    @Schema(description = "manifest JSON SHA-256")
    private String manifestHash;

    @Schema(description = "wheel 文件路径")
    private String artifactPath;

    @Schema(description = "wheel 文件 SHA-256")
    private String artifactHash;

    @TableField(value = "sandbox_config")
    @Schema(description = "沙箱配置 JSON")
    private String sandboxConfig;

    @TableField(value = "permissions")
    @Schema(description = "权限列表 JSON")
    private String permissions;

    @Schema(description = "是否启用")
    private Boolean enabled;

    @Schema(description = "安装人用户ID")
    private Long installedBy;

    @Schema(description = "安装时间")
    private LocalDateTime installedAt;
}
