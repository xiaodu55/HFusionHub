package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.AgentApproval;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

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

    List<AgentApproval> selectExpiredPending(@Param("now") String now);

    int updateDecision(@Param("id") Long id,
                       @Param("status") String status,
                       @Param("decidedBy") Long decidedBy,
                       @Param("decidedAt") String decidedAt,
                       @Param("reason") String reason);
}
