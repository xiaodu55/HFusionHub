package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.math.BigDecimal;
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

    @Schema(description = "插件类型: package|declarative")
    private String pluginKind;

    @Schema(description = "状态: active|disabled|failed|pending|circuit_open")
    private String status;

    @Schema(description = "manifest JSON SHA-256")
    private String manifestHash;

    @Schema(description = "wheel 文件 MinIO 路径")
    private String artifactPath;

    @Schema(description = "wheel 文件 SHA-256")
    private String artifactHash;

    @TableField(value = "sandbox_config")
    @Schema(description = "沙箱配置 JSON")
    private String sandboxConfig;

    @TableField(value = "permissions")
    @Schema(description = "权限列表 JSON")
    private String permissions;

    @TableField(value = "tool_specs_json")
    @Schema(description = "低代码插件工具声明 JSON")
    private String toolSpecsJson;

    @Schema(description = "是否启用")
    private Boolean enabled;

    @Schema(description = "安装人用户ID")
    private Long installedBy;

    @Schema(description = "所属租户ID")
    private Long tenantId;

    @Schema(description = "安装时间")
    private LocalDateTime installedAt;

    @Schema(description = "金丝雀流量权重 (0.00-1.00)")
    private BigDecimal canaryWeight;

    @Schema(description = "熔断器开启截止时间")
    private LocalDateTime circuitOpenUntil;

    @Schema(description = "上一版本（用于回滚）")
    private String previousVersion;

    @Schema(description = "健康状态: healthy|unhealthy|unknown")
    private String healthStatus;

    @Schema(description = "最近健康检查时间")
    private LocalDateTime lastHealthCheck;

    @Schema(description = "CycloneDX SBOM JSON")
    private String sbomJson;

    @Schema(description = "漏洞状态: clean|vulnerable|pending|error")
    private String vulnerabilityStatus;

    @Schema(description = "最近漏洞扫描时间")
    private LocalDateTime lastScanAt;

    @Schema(description = "Docker 镜像标签")
    private String containerImage;

    @Schema(description = "Docker 镜像 SHA-256 摘要，用于供应链完整性校验")
    private String imageDigest;
}
