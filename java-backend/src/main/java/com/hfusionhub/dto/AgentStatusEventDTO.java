package com.hfusionhub.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Data;

/**
 * Agent 状态事件 DTO
 *
 * @author HFusionHub Team
 */
@Data
@Builder
@Schema(description = "Agent状态事件")
public class AgentStatusEventDTO {

    @Schema(description = "事件ID（单调递增，SSE断点续传）")
    private Long id;

    @Schema(description = "任务ID")
    private Long taskId;

    @Schema(description = "运行ID")
    private Long runId;

    @Schema(description = "事件类型")
    private String eventType;

    @Schema(description = "事件发生时任务状态")
    private String status;

    @Schema(description = "附加载荷")
    private Object payload;

    @Schema(description = "创建时间")
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createdAt;
}
