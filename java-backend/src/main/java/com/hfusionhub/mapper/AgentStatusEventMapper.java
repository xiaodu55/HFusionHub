package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.AgentStatusEvent;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Agent 状态事件 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface AgentStatusEventMapper extends BaseMapper<AgentStatusEvent> {

    /**
     * 按任务ID查询事件（支持断点续传 sinceId）
     */
    List<AgentStatusEvent> selectAfter(@Param("taskId") Long taskId,
                                        @Param("sinceId") Long sinceId,
                                        @Param("limit") int limit);

    /**
     * 按任务ID查询最新一条事件
     */
    AgentStatusEvent selectLatestByTaskId(@Param("taskId") Long taskId);

    /**
     * 清理过期事件
     */
    int deleteOlderThan(@Param("cutoff") LocalDateTime cutoff);
}
