package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.PromptTemplate;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface PromptTemplateMapper extends BaseMapper<PromptTemplate> {

    @Select("SELECT * FROM prompt_template WHERE id = #{id}")
    PromptTemplate selectIncludingDeleted(@Param("id") Long id);

    @Select("""
            SELECT * FROM prompt_template
            WHERE user_id = #{userId} AND deleted = 1
              AND (#{keyword} IS NULL OR #{keyword} = ''
                   OR name LIKE CONCAT('%', #{keyword}, '%')
                   OR description LIKE CONCAT('%', #{keyword}, '%'))
            ORDER BY recycled_at DESC, id DESC
            """)
    List<PromptTemplate> selectRecycle(@Param("userId") Long userId,
                                       @Param("keyword") String keyword);

    @Update("""
            UPDATE prompt_template
            SET deleted = 1,
                recycled_at = #{recycledAt},
                recycle_expires_at = #{recycleExpiresAt},
                updated_at = NOW()
            WHERE id = #{id} AND deleted = 0
            """)
    int markRecycled(@Param("id") Long id,
                     @Param("recycledAt") LocalDateTime recycledAt,
                     @Param("recycleExpiresAt") LocalDateTime recycleExpiresAt);

    @Update("""
            UPDATE prompt_template
            SET deleted = 0,
                recycled_at = NULL,
                recycle_expires_at = NULL,
                updated_at = NOW()
            WHERE id = #{id} AND deleted = 1
            """)
    int restoreFromRecycle(@Param("id") Long id);

    @Delete("DELETE FROM prompt_template WHERE id = #{id} AND deleted = 1")
    int purgeById(@Param("id") Long id);

    @Select("""
            SELECT * FROM prompt_template
            WHERE deleted = 1
              AND recycle_expires_at IS NOT NULL
              AND recycle_expires_at <= NOW()
            ORDER BY recycle_expires_at ASC
            LIMIT #{limit}
            """)
    List<PromptTemplate> selectExpiredRecycled(@Param("limit") int limit);
}
