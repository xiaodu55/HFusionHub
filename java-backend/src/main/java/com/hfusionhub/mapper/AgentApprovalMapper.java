package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.AgentApproval;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * Agent 审批记录 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface AgentApprovalMapper extends BaseMapper<AgentApproval> {

    AgentApproval selectByApprovalId(@Param("approvalId") String approvalId);

    List<AgentApproval> selectByTaskId(@Param("taskId") Long taskId);

    List<AgentApproval> selectPendingByUserId(@Param("userId") Long userId);

    /**
     * Recent approvals (any status) for a user — used by the approvals SSE
     * stream to snapshot + diff live status changes.
     */
    List<AgentApproval> selectRecentByUserId(@Param("userId") Long userId, @Param("limit") int limit);

    /**
     * Move an approved approval to its execution outcome ({@code executed} or
     * {@code failed}) after the Python resume call completes.
     *
     * @return 1 when the approval was still {@code approved} and the outcome was
     *         recorded; 0 otherwise (guarded against double-outcome writes).
     */
    int updateExecutionOutcome(@Param("id") Long id, @Param("status") String status);

    List<AgentApproval> selectExpiredPending(@Param("now") String now);

    int updateDecision(
            @Param("id") Long id,
            @Param("status") String status,
            @Param("decidedBy") Long decidedBy,
            @Param("decidedAt") String decidedAt,
            @Param("reason") String reason);

    /**
     * Issue a one-time execution token for an approved approval.
     *
     * @return 1 when the approval was still pending and the token was issued;
     *         0 when the approval was already decided / not in a state that can
     *           receive a token (duplicate decision protection).
     */
    int issueExecutionToken(
            @Param("id") Long id,
            @Param("token") String token,
            @Param("status") String status,
            @Param("issuedAt") String issuedAt);

    /**
     * Atomically consume a one-time execution token.
     *
     * @return 1 when the token existed, was in {@code issued} state, and is now
     *         {@code consumed}; 0 when it was already consumed / revoked / missing
     *         (a replayed approve/resume is rejected without side effects).
     */
    int consumeExecutionToken(
            @Param("approvalId") String approvalId,
            @Param("token") String token,
            @Param("consumedAt") String consumedAt);
}
