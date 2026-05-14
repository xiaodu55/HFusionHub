package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.AgentStep;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

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
     * 批量按多个运行ID查询所有步骤（避免每 run 一次查询的 N+1）
     */
    List<AgentStep> selectByRunIds(@Param("runIds") List<Long> runIds);

    /**
     * 批量插入步骤（非流式场景）
     */
    int insertBatch(@Param("steps") List<AgentStep> steps);

    /**
     * 按运行ID统计步骤数
     */
    int countByRunId(@Param("runId") Long runId);

    /**
     * 按运行ID删除所有步骤（孤儿重派前清理）
     */
    int deleteByRunId(@Param("runId") Long runId);

    /**
     * 查询当前用户最近的工具调用记录，带任务上下文。
     * JOIN agent_run + agent_task 以获取任务查询文本。
     * 按 agent_task.user_id 过滤，确保用户 A 无法读取用户 B 的记录。
     *
     * @param userId 当前登录用户ID（安全过滤）
     * @param limit  返回条数上限
     * @param offset 偏移量
     * @return 工具调用记录列表
     */
    List<Map<String, Object>> selectRecentToolCalls(
            @Param("userId") Long userId, @Param("limit") int limit, @Param("offset") int offset);

    /**
     * 统计当前用户的工具调用总条数（step_type = 'tool_call'）。
     * 按 agent_task.user_id 过滤。
     */
    int countToolCalls(@Param("userId") Long userId);
}
