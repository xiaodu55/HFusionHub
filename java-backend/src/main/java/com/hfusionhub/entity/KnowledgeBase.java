package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 知识库实体
 *
 * @author HFusionHub Team
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("knowledge_base")
@Schema(description = "知识库实体")
public class KnowledgeBase extends BaseEntity {

    /** 知识库分类（招投标垂直化） */
    public static final String CATEGORY_GENERAL = "general";
    public static final String CATEGORY_TENDER = "tender";
    public static final String CATEGORY_QUALIFICATION = "qualification";
    public static final String CATEGORY_BID_HISTORY = "bid_history";

    /** 状态：0-正常，1-禁用 */
    public static final Integer STATUS_NORMAL = 0;
    public static final Integer STATUS_DISABLED = 1;

    /**
     * 知识库ID
     */
    @TableId(type = IdType.AUTO)
    @Schema(description = "知识库ID")
    private Long id;

    /**
     * 知识库名称
     */
    @Schema(description = "知识库名称")
    private String name;

    /**
     * 知识库描述
     */
    @Schema(description = "知识库描述")
    private String description;

    /**
     * 创建者ID
     */
    @Schema(description = "创建者ID")
    private Long userId;

    /**
     * 状态：0-正常，1-禁用
     */
    @Schema(description = "状态：0-正常，1-禁用")
    private Integer status;

    /** 移入回收站时间 */
    private LocalDateTime recycledAt;

    /** 回收站保留截止时间 */
    private LocalDateTime recycleExpiresAt;

    /**
     * 知识库分类（招投标垂直化）：general|tender|qualification|bid_history
     */
    @Schema(description = "知识库分类：general|tender|qualification|bid_history")
    private String category;

    /**
     * 文档数量（非数据库字段）
     */
    @TableField(exist = false)
    @Schema(description = "文档数量")
    private Integer documentCount;
}
