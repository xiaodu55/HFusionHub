package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.AgentRecoveryEvent;
import org.apache.ibatis.annotations.Mapper;

/**
 * Agent 恢复审计事件 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface AgentRecoveryEventMapper extends BaseMapper<AgentRecoveryEvent> {
}
