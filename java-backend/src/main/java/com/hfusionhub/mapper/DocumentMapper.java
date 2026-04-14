package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.Document;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;
import java.util.List;

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

    @Select("SELECT COUNT(*) FROM document WHERE knowledge_base_id = #{knowledgeBaseId}")
    int countByKnowledgeBaseIncludingDeleted(@Param("knowledgeBaseId") Long knowledgeBaseId);

    @Select("SELECT * FROM document WHERE id = #{id}")
    Document selectIncludingDeleted(@Param("id") Long id);

    @Select("SELECT * FROM document WHERE knowledge_base_id = #{knowledgeBaseId}")
    List<Document> selectByKnowledgeBaseIncludingDeleted(@Param("knowledgeBaseId") Long knowledgeBaseId);

    @Select("SELECT * FROM document ORDER BY id")
    List<Document> selectAllIncludingDeleted();

    @Select("""
            SELECT d.* FROM document d
            JOIN knowledge_base kb ON kb.id = d.knowledge_base_id
            WHERE d.deleted = 1
              AND kb.user_id = #{userId}
              AND (#{title} IS NULL OR #{title} = '' OR d.title LIKE CONCAT('%', #{title}, '%'))
            ORDER BY d.recycled_at DESC, d.id DESC
            LIMIT #{offset}, #{size}
            """)
    List<Document> selectRecyclePage(@Param("userId") Long userId,
                                     @Param("title") String title,
                                     @Param("offset") int offset,
                                     @Param("size") int size);

    @Select("""
            SELECT COUNT(*) FROM document d
            JOIN knowledge_base kb ON kb.id = d.knowledge_base_id
            WHERE d.deleted = 1
              AND kb.user_id = #{userId}
              AND (#{title} IS NULL OR #{title} = '' OR d.title LIKE CONCAT('%', #{title}, '%'))
            """)
    long countRecycle(@Param("userId") Long userId, @Param("title") String title);

    @Select("""
            SELECT * FROM document
            WHERE deleted = 1
              AND recycle_expires_at IS NOT NULL
              AND recycle_expires_at <= NOW()
            ORDER BY recycle_expires_at ASC
            LIMIT #{limit}
            """)
    List<Document> selectExpiredRecycled(@Param("limit") int limit);

    @Update("""
            UPDATE document
            SET deleted = 1,
                recycled_at = #{recycledAt},
                recycle_expires_at = #{recycleExpiresAt},
                status = #{status},
                chunk_count = 0,
                processed_at = NULL,
                error_message = #{errorMessage},
                updated_at = NOW()
            WHERE id = #{id} AND deleted = 0
            """)
    int markRecycled(@Param("id") Long id,
                     @Param("recycledAt") LocalDateTime recycledAt,
                     @Param("recycleExpiresAt") LocalDateTime recycleExpiresAt,
                     @Param("status") Integer status,
                     @Param("errorMessage") String errorMessage);

    @Update("""
            UPDATE document
            SET deleted = 0,
                recycled_at = NULL,
                recycle_expires_at = NULL,
                status = #{status},
                chunk_count = 0,
                processed_at = NULL,
                error_message = NULL,
                updated_at = NOW()
            WHERE id = #{id} AND deleted = 1
            """)
    int restoreFromRecycle(@Param("id") Long id, @Param("status") Integer status);

    @Delete("DELETE FROM document WHERE id = #{id}")
    int purgeById(@Param("id") Long id);
}
