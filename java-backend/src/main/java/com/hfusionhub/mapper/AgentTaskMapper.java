package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.AgentTask;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/**
 * Agent 任务 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface AgentTaskMapper extends BaseMapper<AgentTask> {

    /**
     * 按幂等键查询任务
     */
    AgentTask selectByRequestId(@Param("requestId") String requestId);

    /**
     * 按用户和状态查询任务列表（分页用）
     */
    List<AgentTask> selectByUserIdAndStatus(@Param("userId") Long userId,
                                            @Param("status") String status,
                                            @Param("offset") int offset,
                                            @Param("limit") int limit);

    /**
     * 按用户统计任务数
     */
    int countByUserIdAndStatus(@Param("userId") Long userId,
                               @Param("status") String status);

    /**
     * 更新任务状态和当前运行ID
     */
    int updateStatus(@Param("id") Long id,
                     @Param("status") String status,
                     @Param("currentRunId") Long currentRunId);
}
