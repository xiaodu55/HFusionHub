package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.AgentRun;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/**
 * Agent 运行记录 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface AgentRunMapper extends BaseMapper<AgentRun> {

    /**
     * 按 UUID 查询运行记录
     */
    AgentRun selectByRunUuid(@Param("runUuid") String runUuid);

    /**
     * 按任务ID查询所有运行记录
     */
    List<AgentRun> selectByTaskId(@Param("taskId") Long taskId);

    /**
     * 更新运行记录的终态信息
     */
    int updateFinalStatus(@Param("id") Long id,
                          @Param("status") String status,
                          @Param("model") String model,
                          @Param("tokenUsage") String tokenUsage,
                          @Param("toolCallsCount") Integer toolCallsCount,
                          @Param("durationMs") Long durationMs,
                          @Param("errorCode") String errorCode,
                          @Param("errorDetail") String errorDetail,
                          @Param("failedTool") String failedTool,
                          @Param("completedAt") String completedAt);
}
