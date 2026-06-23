package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.DocumentIndexJob;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface DocumentIndexJobMapper extends BaseMapper<DocumentIndexJob> {

    @Select("SELECT * FROM document_index_job WHERE document_id = #{documentId} "
            + "AND deleted = 0 ORDER BY id DESC LIMIT 1")
    DocumentIndexJob selectLatestByDocumentId(@Param("documentId") Long documentId);

    @Select("SELECT COUNT(*) FROM document_index_job WHERE document_id = #{documentId} AND deleted = 0")
    int countByDocumentId(@Param("documentId") Long documentId);

    /**
     * 文档当前最大尝试号（V77/S5）：配合文档行锁替代 count+1 计算，消除 TOCTOU
     */
    @Select("SELECT COALESCE(MAX(attempt), 0) FROM document_index_job WHERE document_id = #{documentId} AND deleted = 0")
    int selectMaxAttemptByDocumentId(@Param("documentId") Long documentId);

    @Select("SELECT * FROM document_index_job WHERE status = 'PROCESSING' AND deleted = 0 "
            + "AND started_at < #{before} AND attempt < #{maxAttempts} ORDER BY id ASC")
    List<DocumentIndexJob> selectStaleProcessingJobs(
            @Param("before") LocalDateTime before, @Param("maxAttempts") int maxAttempts);

    @Select("SELECT * FROM document_index_job WHERE status = 'PROCESSING' AND deleted = 0 "
            + "AND started_at < #{before} AND attempt >= #{maxAttempts} ORDER BY id ASC")
    List<DocumentIndexJob> selectExhaustedProcessingJobs(
            @Param("before") LocalDateTime before, @Param("maxAttempts") int maxAttempts);

    @Delete("DELETE FROM document_index_job WHERE document_id = #{documentId}")
    int purgeByDocumentId(@Param("documentId") Long documentId);
}
