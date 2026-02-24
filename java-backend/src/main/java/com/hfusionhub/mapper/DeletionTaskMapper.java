package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.DeletionTask;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 删除任务 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface DeletionTaskMapper extends BaseMapper<DeletionTask> {

    @Select("SELECT * FROM deletion_task WHERE status IN ('PENDING','RETRYING') ORDER BY created_at ASC LIMIT #{limit}")
    List<DeletionTask> selectPendingTasks(@Param("limit") int limit);

    @Update("""
            UPDATE deletion_task
            SET status = 'RETRYING',
                error_message = #{errorMessage},
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'PROCESSING'
              AND updated_at < #{staleBefore}
              AND retry_count < max_retries
            """)
    int recoverStaleProcessingTasks(@Param("staleBefore") LocalDateTime staleBefore,
                                    @Param("errorMessage") String errorMessage);

    @Select("SELECT * FROM deletion_task WHERE status = 'FAILED' AND retry_count < max_retries ORDER BY created_at ASC LIMIT #{limit}")
    List<DeletionTask> selectRetryableTasks(@Param("limit") int limit);

    @Select("""
            SELECT * FROM deletion_task
            WHERE task_type = #{taskType}
              AND target_id = #{targetId}
              AND status IN ('PENDING', 'PROCESSING', 'RETRYING')
            ORDER BY id DESC
            LIMIT 1
            """)
    DeletionTask selectActiveTask(@Param("taskType") String taskType, @Param("targetId") Long targetId);
}
