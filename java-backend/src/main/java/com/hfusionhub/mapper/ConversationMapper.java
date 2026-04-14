package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.Conversation;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * 对话 Mapper 接口
 *
 * @author HFusionHub Team
 */
@Mapper
public interface ConversationMapper extends BaseMapper<Conversation> {

    @Select("SELECT * FROM conversation WHERE knowledge_base_id = #{knowledgeBaseId}")
    List<Conversation> selectByKnowledgeBaseIncludingDeleted(@Param("knowledgeBaseId") Long knowledgeBaseId);

    @Delete("DELETE FROM conversation WHERE id = #{id}")
    int purgeById(@Param("id") Long id);
}
