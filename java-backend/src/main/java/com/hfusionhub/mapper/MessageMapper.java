package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.Message;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * 消息 Mapper 接口
 *
 * @author HFusionHub Team
 */
@Mapper
public interface MessageMapper extends BaseMapper<Message> {

    /**
     * 按对话ID查询消息列表
     * SQL 定义在 MessageMapper.xml 中
     */
    List<Message> selectByConversationId(@Param("conversationId") Long conversationId);

    /**
     * 批量聚合查询——一次 SQL 获取每个对话的消息数量和最新消息
     */
    List<Map<String, Object>> aggregateByConversationIds(@Param("ids") List<Long> conversationIds);
}
