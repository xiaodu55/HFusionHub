package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.Document;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/**
 * 文档 Mapper 接口
 *
 * @author HFusionHub Team
 */
@Mapper
public interface DocumentMapper extends BaseMapper<Document> {

    /**
     * 统计知识库下的文档数量
     *
     * @param knowledgeBaseId 知识库ID
     * @return 文档数量
     */
    @Select("SELECT COUNT(*) FROM document WHERE knowledge_base_id = #{knowledgeBaseId} AND deleted = 0")
    int countByKnowledgeBaseId(@Param("knowledgeBaseId") Long knowledgeBaseId);
}
