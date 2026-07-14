package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * Agent 步骤成功率(Spark ADS 镜像)。
 *
 * @author HFusionHub Team
 */
@Data
@TableName("ads_tool_success")
public class AdsToolSuccess {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long tenantId;

    private String stepType;

    private LocalDate statDate;

    private Long stepCount;

    private Long errorCount;

    private Double successRate;

    private LocalDateTime createdAt;
}
