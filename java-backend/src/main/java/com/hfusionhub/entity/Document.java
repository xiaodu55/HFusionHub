package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

/**
 * 文档实体
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("document")
@Schema(description = "文档实体")
public class Document extends BaseEntity {

    /**
     * 文档ID
     */
    @TableId(type = IdType.AUTO)
    @Schema(description = "文档ID")
    private Long id;

    /**
     * 知识库ID
     */
    @Schema(description = "知识库ID")
    private Long knowledgeBaseId;

    /**
     * 文档标题
     */
    @Schema(description = "文档标题")
    private String title;

    /**
     * 文档内容
     */
    @Schema(description = "文档内容")
    private String content;

    /**
     * 文件路径
     */
    @Schema(description = "文件路径")
    private String filePath;

    /**
     * 文件类型
     */
    @Schema(description = "文件类型")
    private String fileType;

    /**
     * 文件大小（字节）
     */
    @Schema(description = "文件大小（字节）")
    private Long fileSize;

    /**
     * 分块数量
     */
    @Schema(description = "分块数量")
    private Integer chunkCount;

    /**
     * 状态：0-待解析，1-解析中，2-已完成，3-失败
     */
    @Schema(description = "状态：0-待解析，1-解析中，2-已完成，3-失败")
    private Integer status;

    /**
     * 错误信息
     */
    @Schema(description = "错误信息")
    private String errorMessage;

    /**
     * 处理完成时间
     */
    @Schema(description = "处理完成时间")
    private LocalDateTime processedAt;
}
