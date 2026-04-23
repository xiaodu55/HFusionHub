package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.hfusionhub.handler.JsonTypeHandler;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import lombok.Data;

/**
 * 消息实体
 *
 * @author HFusionHub Team
 */
@Data
@TableName("message")
@Schema(description = "消息实体")
public class Message {

    /**
     * 消息ID
     */
    @TableId(type = IdType.AUTO)
    @Schema(description = "消息ID")
    private Long id;

    /**
     * 对话ID
     */
    @Schema(description = "对话ID")
    private Long conversationId;

    /**
     * 角色：user-用户，assistant-助手，system-系统
     */
    @Schema(description = "角色：user-用户，assistant-助手，system-系统")
    private String role;

    /**
     * 消息内容
     */
    @Schema(description = "消息内容")
    private String content;

    /**
     * Token数量
     */
    @Schema(description = "Token数量")
    private Integer tokenCount;

    /**
     * 使用的模型
     */
    @Schema(description = "使用的模型")
    private String model;

    /**
     * 知识来源
     */
    @TableField(typeHandler = JsonTypeHandler.class)
    @Schema(description = "知识来源")
    private List<Map<String, Object>> sources;

    /**
     * 创建时间
     */
    @TableField(fill = FieldFill.INSERT)
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;

    /**
     * 更新时间
     */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    @Schema(description = "更新时间")
    private LocalDateTime updatedAt;

    /**
     * 客户端请求幂等ID
     */
    @Schema(description = "客户端请求幂等ID")
    private String requestId;
}
