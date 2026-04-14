package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.KnowledgeBase;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 知识库 Mapper 接口
 *
 * @author HFusionHub Team
 */
@Mapper
public interface KnowledgeBaseMapper extends BaseMapper<KnowledgeBase> {

    @Select("SELECT * FROM knowledge_base WHERE id = #{id}")
    KnowledgeBase selectIncludingDeleted(@Param("id") Long id);

    @Select("""
            SELECT * FROM knowledge_base
            WHERE deleted = 1
              AND user_id = #{userId}
              AND (#{name} IS NULL OR #{name} = '' OR name LIKE CONCAT('%', #{name}, '%'))
            ORDER BY recycled_at DESC, id DESC
            LIMIT #{offset}, #{size}
            """)
    List<KnowledgeBase> selectRecyclePage(@Param("userId") Long userId,
                                           @Param("name") String name,
                                           @Param("offset") int offset,
                                           @Param("size") int size);

    @Select("""
            SELECT COUNT(*) FROM knowledge_base
            WHERE deleted = 1
              AND user_id = #{userId}
              AND (#{name} IS NULL OR #{name} = '' OR name LIKE CONCAT('%', #{name}, '%'))
            """)
    long countRecycle(@Param("userId") Long userId, @Param("name") String name);

    @Select("""
            SELECT * FROM knowledge_base
            WHERE deleted = 1
              AND recycle_expires_at IS NOT NULL
              AND recycle_expires_at <= NOW()
            ORDER BY recycle_expires_at ASC
            LIMIT #{limit}
            """)
    List<KnowledgeBase> selectExpiredRecycled(@Param("limit") int limit);

    @Update("""
            UPDATE knowledge_base
            SET deleted = 1,
                recycled_at = #{recycledAt},
                recycle_expires_at = #{recycleExpiresAt},
                status = #{status},
                updated_at = NOW()
            WHERE id = #{id} AND deleted = 0
            """)
    int markRecycled(@Param("id") Long id,
                     @Param("recycledAt") LocalDateTime recycledAt,
                     @Param("recycleExpiresAt") LocalDateTime recycleExpiresAt,
                     @Param("status") Integer status);

    @Update("""
            UPDATE knowledge_base
            SET deleted = 0,
                recycled_at = NULL,
                recycle_expires_at = NULL,
                status = #{status},
                updated_at = NOW()
            WHERE id = #{id} AND deleted = 1
            """)
    int restoreFromRecycle(@Param("id") Long id, @Param("status") Integer status);

    @Delete("DELETE FROM knowledge_base WHERE id = #{id}")
    int purgeById(@Param("id") Long id);
}
