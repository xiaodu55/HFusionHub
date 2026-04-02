package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.*;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 插件依赖锁定实体
 *
 * @author HFusionHub Team
 */
@Data
@TableName("plugin_dependency")
@Schema(description = "插件依赖锁定")
public class PluginDependency {

    @TableId(type = IdType.AUTO)
    @Schema(description = "记录ID")
    private Long id;

    @Schema(description = "关联插件ID")
    private Long pluginId;

    @Schema(description = "依赖名称")
    private String dependencyName;

    @Schema(description = "依赖版本范围")
    private String dependencyVersion;

    @Schema(description = "是否可选依赖")
    private Boolean optional;

    @Schema(description = "创建时间")
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
