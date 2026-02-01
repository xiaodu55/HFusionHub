package com.hfusionhub.service;

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
     */
    void startVectorization(Long documentId);

    /**
     * 获取文档分块列表
     *
     * @param documentId 文档ID
     * @param page       页码
     * @param size       每页大小
     * @param blockType  块类型筛选（可选）
     * @return 分块列表JSON
     */
    String getDocumentChunks(Long documentId, Integer page, Integer size, String blockType);

    /**
     * 获取单个分块详情
     *
     * @param chunkId 分块ID
     * @return 分块详情JSON
     */
    String getChunkDetail(String chunkId);

    /**
     * 回调：更新文档处理状态
     *
     * @param documentId 文档ID
     * @param status     状态
     * @param chunkCount 分块数量
     */
    void updateDocumentStatus(Long documentId, String status, Integer chunkCount);

    /**
     * 同步文档状态：从Python引擎查询实际分块数，更新数据库状态
     *
     * @param documentId 文档ID
     */
    void syncDocumentStatus(Long documentId);
}
