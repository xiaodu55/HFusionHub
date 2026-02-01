package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.Conversation;
import org.apache.ibatis.annotations.Mapper;

/**
 * 对话 Mapper 接口
 *
 * @author HFusionHub Team
 */
@Mapper
public interface ConversationMapper extends BaseMapper<Conversation> {
}
