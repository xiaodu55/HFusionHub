package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.DocumentIndexJob;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface DocumentIndexJobMapper extends BaseMapper<DocumentIndexJob> {

    @Select("SELECT * FROM document_index_job WHERE document_id = #{documentId} "
            + "AND deleted = 0 ORDER BY id DESC LIMIT 1")
    DocumentIndexJob selectLatestByDocumentId(@Param("documentId") Long documentId);

    @Select("SELECT COUNT(*) FROM document_index_job WHERE document_id = #{documentId} AND deleted = 0")
    int countByDocumentId(@Param("documentId") Long documentId);

    @Select("SELECT * FROM document_index_job WHERE status = 'PROCESSING' AND deleted = 0 "
            + "AND started_at < #{before} AND attempt < #{maxAttempts} ORDER BY id ASC")
    List<DocumentIndexJob> selectStaleProcessingJobs(@Param("before") LocalDateTime before,
                                                      @Param("maxAttempts") int maxAttempts);

    @Select("SELECT * FROM document_index_job WHERE status = 'PROCESSING' AND deleted = 0 "
            + "AND started_at < #{before} AND attempt >= #{maxAttempts} ORDER BY id ASC")
    List<DocumentIndexJob> selectExhaustedProcessingJobs(@Param("before") LocalDateTime before,
                                                          @Param("maxAttempts") int maxAttempts);

    @Delete("DELETE FROM document_index_job WHERE document_id = #{documentId}")
    int purgeByDocumentId(@Param("documentId") Long documentId);
}
