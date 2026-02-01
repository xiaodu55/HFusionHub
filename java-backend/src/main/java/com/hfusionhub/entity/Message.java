package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

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
     * 创建时间
     */
    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
