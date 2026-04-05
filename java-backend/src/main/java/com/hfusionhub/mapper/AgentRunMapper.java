package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.AgentRun;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.time.LocalDateTime;
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

    // ================================================================
    // V13: 异步任务调度 — 队列/租约/恢复方法
    // ================================================================

    /**
     * 条件租约认领：仅当仍为 pending 且到达计划时间才认领成功
     * @return 影响行数（1=成功, 0=已被认领或未到时间）
     */
    int claimRun(@Param("id") Long id,
                 @Param("holder") String holder,
                 @Param("leaseExpiresAt") LocalDateTime leaseExpiresAt,
                 @Param("now") LocalDateTime now,
                 @Param("heartbeatAt") LocalDateTime heartbeatAt);

    /**
     * 队列轮询：获取待执行的 pending Run
     */
    List<AgentRun> selectQueuedRuns(@Param("now") LocalDateTime now,
                                    @Param("limit") int limit);

    /**
     * 孤儿检测：running 但租约已过期的 Run
     */
    List<AgentRun> selectLeaseExpiredRuns(@Param("staleBefore") LocalDateTime staleBefore,
                                          @Param("limit") int limit);

    /**
     * 心跳续租（holder 匹配才生效）
     * @return 影响行数
     */
    int renewLease(@Param("id") Long id,
                   @Param("holder") String holder,
                   @Param("leaseExpiresAt") LocalDateTime leaseExpiresAt,
                   @Param("heartbeatAt") LocalDateTime heartbeatAt);

    /**
     * 释放租约
     * @return 影响行数
     */
    int releaseLease(@Param("id") Long id,
                     @Param("holder") String holder);

    /**
     * 终态守护写入：仅 running/waiting_approval 可写入终态（拒绝过期回调）
     * @return 影响行数（0=状态不匹配，回调已过期）
     */
    int completeRunGuarded(@Param("id") Long id,
                           @Param("status") String status,
                           @Param("errorCode") String errorCode,
                           @Param("errorDetail") String errorDetail,
                           @Param("failedTool") String failedTool,
                           @Param("completedAt") LocalDateTime completedAt);

    /** Persist metadata only after {@link #completeRunGuarded} won the terminal-state race. */
    int updateCompletionMetadata(@Param("id") Long id,
                                 @Param("model") String model,
                                 @Param("tokenUsage") java.util.Map<String, Object> tokenUsage,
                                 @Param("toolCallsCount") Integer toolCallsCount,
                                 @Param("durationMs") Long durationMs);

    /**
     * 孤儿重派：重置为 pending, 换新 UUID, 计数+1, 清空执行痕迹
     * @return 影响行数
     */
    int requeueOrphan(@Param("id") Long id,
                      @Param("runUuid") String runUuid,
                      @Param("scheduledAt") LocalDateTime scheduledAt);

    /**
     * 按租约持有者查询活跃 Run
     */
    List<AgentRun> selectByHolder(@Param("holder") String holder);
}
