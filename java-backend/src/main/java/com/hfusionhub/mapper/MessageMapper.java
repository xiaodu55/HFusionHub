package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.Message;
import com.hfusionhub.handler.JsonTypeHandler;
import org.apache.ibatis.annotations.*;

import java.util.List;

/**
 * 消息 Mapper 接口
 *
 * @author HFusionHub Team
 */
@Mapper
public interface MessageMapper extends BaseMapper<Message> {

    /**
     * 按对话ID查询消息列表（使用 @Results 确保 sources JSON 正确反序列化）
     */
    @Select("SELECT id, conversation_id, role, content, token_count, model, sources, created_at, updated_at " +
            "FROM message WHERE conversation_id = #{conversationId} ORDER BY created_at ASC")
    @Results(id = "messageWithSources", value = {
            @Result(id = true, column = "id", property = "id"),
            @Result(column = "conversation_id", property = "conversationId"),
            @Result(column = "role", property = "role"),
            @Result(column = "content", property = "content"),
            @Result(column = "token_count", property = "tokenCount"),
            @Result(column = "model", property = "model"),
            @Result(column = "sources", property = "sources", typeHandler = JsonTypeHandler.class),
            @Result(column = "created_at", property = "createdAt"),
            @Result(column = "updated_at", property = "updatedAt")
    })
    List<Message> selectByConversationId(@Param("conversationId") Long conversationId);
}
