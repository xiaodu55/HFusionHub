package com.hfusionhub.service;

import com.hfusionhub.dto.ChunkDTO;
import com.hfusionhub.dto.ChunkPageDTO;
import com.hfusionhub.dto.DocumentIndexCallbackDTO;

/**
 * 向量化服务接口
 *
 * @author HFusionHub Team
 */
public interface VectorizationService {

    /**
     * 触发文档向量化
     *
     * @param documentId 文档ID
     * @param model      嵌入模型（可选）
     */
    void startVectorization(Long documentId, String model);

    /**
     * 获取文档分块列表
     *
     * @param documentId 文档ID
     * @param page       页码
     * @param size       每页大小
     * @param blockType  块类型筛选（可选）
     * @return 分页分块列表
     */
    ChunkPageDTO getDocumentChunks(Long documentId, Integer page, Integer size, String blockType);

    /**
     * 获取单个分块详情。
     *
     * <p>分块不存在时抛出 {@code BusinessException(StatusCode.CHUNK_NOT_FOUND)}，
     * 由 {@link com.hfusionhub.common.exception.GlobalExceptionHandler} 转换为 HTTP 404。</p>
     *
     * @param chunkId 分块ID
     * @return 分块详情
     */
    ChunkDTO getChunkDetail(String chunkId);

    /**
     * 回调：更新文档处理状态
     *
     * @param documentId 文档ID
     * @param status     状态
     * @param chunkCount 分块数量
     */
    void updateDocumentStatus(Long documentId, DocumentIndexCallbackDTO callback);

    /** Remove a document's vector entries and durable chunk metadata. */
    void deleteDocumentIndex(Long documentId);

    /** Re-submit interrupted indexing jobs that have exceeded the stale timeout. */
    int recoverStaleIndexJobs();

    /**
     * 同步文档状态：从Python引擎查询实际分块数，更新数据库状态
     *
     * @param documentId 文档ID
     */
    void syncDocumentStatus(Long documentId);

    /**
     * 同步所有待处理文档的状态
     *
     * @return 同步的文档数量
     */
    int syncAllDocuments();

    /**
     * 重置文档状态为待解析
     *
     * @param documentId 文档ID
     */
    void resetDocument(Long documentId);

    /**
     * 获取文档处理任务状态（从Python引擎查询）
     *
     * @param documentId 文档ID
     * @return 任务状态JSON
     */
    String getTaskStatus(Long documentId);
}
