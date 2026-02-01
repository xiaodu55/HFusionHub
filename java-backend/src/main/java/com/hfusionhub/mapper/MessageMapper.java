package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.Message;
import org.apache.ibatis.annotations.Mapper;

/**
 * 消息 Mapper 接口
 *
 * @author HFusionHub Team
 */
@Mapper
public interface MessageMapper extends BaseMapper<Message> {
}
