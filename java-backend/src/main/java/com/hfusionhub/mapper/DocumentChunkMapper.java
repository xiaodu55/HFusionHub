package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.DocumentChunk;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface DocumentChunkMapper extends BaseMapper<DocumentChunk> {

    @Delete("DELETE FROM document_chunk WHERE document_id = #{documentId}")
    int deleteByDocumentId(@Param("documentId") Long documentId);

    @Select({"<script>",
            "SELECT * FROM document_chunk WHERE document_id = #{documentId}",
            "<if test='blockType != null and blockType != \"\"'> AND block_type = #{blockType}</if>",
            "ORDER BY chunk_index ASC LIMIT #{offset}, #{size}",
            "</script>"})
    List<DocumentChunk> selectPageByDocumentId(@Param("documentId") Long documentId,
                                               @Param("offset") int offset,
                                               @Param("size") int size,
                                               @Param("blockType") String blockType);

    @Select({"<script>",
            "SELECT COUNT(*) FROM document_chunk WHERE document_id = #{documentId}",
            "<if test='blockType != null and blockType != \"\"'> AND block_type = #{blockType}</if>",
            "</script>"})
    long countByDocumentId(@Param("documentId") Long documentId, @Param("blockType") String blockType);

    /**
     * 按分块主键精确查询。
     *
     * <p>显式 SQL 避免依赖 MyBatis Plus {@code selectById} 的隐式映射，
     * 同时为后续 DBA 优化（索引提示、分区裁剪）留下锚点。</p>
     */
    @Select("SELECT chunk_id, document_id, knowledge_base_id, index_version, "
            + "chunk_index, block_type, outline_path, content_excerpt, char_count, metadata "
            + "FROM document_chunk WHERE chunk_id = #{chunkId}")
    DocumentChunk selectByChunkId(@Param("chunkId") String chunkId);
}
