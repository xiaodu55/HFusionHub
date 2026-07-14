package com.hfusionhub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Data;

/**
 * 大数据批处理执行日志(Sqoop/Spark/质量门禁的调度与手工回补记录)。
 *
 * @author HFusionHub Team
 */
@Data
@TableName("bigdata_batch_run_log")
public class BigDataBatchRunLog {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 触发者租户(手工回补记录;日终调度为 NULL) */
    private Long tenantId;

    /** full-import | dwd-transform | dws-aggregate | quality-check | ads-build | pipeline */
    private String jobName;

    private LocalDate batchDate;

    /** 执行命令(脱敏后) */
    private String command;

    /** RUNNING | SUCCESS | FAILED | SKIPPED */
    private String status;

    private Integer exitCode;

    private LocalDateTime startedAt;

    private LocalDateTime finishedAt;

    private Long durationMs;

    private String logExcerpt;

    private LocalDateTime createdAt;
}
