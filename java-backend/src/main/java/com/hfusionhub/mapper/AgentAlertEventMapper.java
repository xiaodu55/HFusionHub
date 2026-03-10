package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.AgentAlertEvent;
import org.apache.ibatis.annotations.Mapper;

/**
 * Agent 告警事件 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface AgentAlertEventMapper extends BaseMapper<AgentAlertEvent> {
}
