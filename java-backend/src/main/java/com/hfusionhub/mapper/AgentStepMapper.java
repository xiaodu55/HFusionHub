package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.AgentStep;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/**
 * Agent 步骤记录 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface AgentStepMapper extends BaseMapper<AgentStep> {

    /**
     * 按运行ID查询所有步骤（按序号排序）
     */
    List<AgentStep> selectByRunId(@Param("runId") Long runId);

    /**
     * 批量插入步骤（非流式场景）
     */
    int insertBatch(@Param("steps") List<AgentStep> steps);

    /**
     * 按运行ID统计步骤数
     */
    int countByRunId(@Param("runId") Long runId);
}
