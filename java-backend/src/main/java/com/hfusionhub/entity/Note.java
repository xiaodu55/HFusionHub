package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 用户笔记（写笔记闭环）
 *
 * <p>由 Agent 的 write_note 工具（经内部端点）或用户笔记管理 API 写入。</p>
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("note")
@Schema(description = "用户笔记")
public class Note extends BaseEntity {

    @TableId(type = IdType.AUTO)
    @Schema(description = "笔记ID")
    private Long id;

    @Schema(description = "所属用户ID")
    private Long userId;

    @Schema(description = "所属租户ID")
    private Long tenantId;

    @Schema(description = "关联知识库ID（可空）")
    private Long knowledgeBaseId;

    @Schema(description = "来源会话ID（可空）")
    private Long conversationId;

    @Schema(description = "来源消息ID（可空）")
    private Long messageId;

    @Schema(description = "笔记标题")
    private String title;

    @Schema(description = "笔记内容（Markdown）")
    private String content;

    @Schema(description = "来源: manual|agent_write_note")
    private String source;
}
