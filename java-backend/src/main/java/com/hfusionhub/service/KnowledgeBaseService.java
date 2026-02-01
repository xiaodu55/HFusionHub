package com.hfusionhub.service;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.dto.KnowledgeBaseCreateDTO;
import com.hfusionhub.dto.KnowledgeBaseInfoDTO;
import com.hfusionhub.dto.KnowledgeBaseQueryDTO;
import com.hfusionhub.dto.KnowledgeBaseUpdateDTO;

/**
 * 知识库服务接口
 *
 * @author HFusionHub Team
 */
public interface KnowledgeBaseService {

    /**
     * 创建知识库
     *
     * @param createDTO 创建请求
     * @return 知识库信息
     */
    KnowledgeBaseInfoDTO create(KnowledgeBaseCreateDTO createDTO);

    /**
     * 更新知识库
     *
     * @param id        知识库ID
     * @param updateDTO 更新请求
     * @return 知识库信息
     */
    KnowledgeBaseInfoDTO update(Long id, KnowledgeBaseUpdateDTO updateDTO);

    /**
     * 删除知识库
     *
     * @param id 知识库ID
     */
    void delete(Long id);

    /**
     * 根据ID获取知识库信息
     *
     * @param id 知识库ID
     * @return 知识库信息
     */
    KnowledgeBaseInfoDTO getById(Long id);

    /**
     * 分页查询知识库列表
     *
     * @param queryDTO 查询条件
     * @return 分页结果
     */
    PageResult<KnowledgeBaseInfoDTO> list(KnowledgeBaseQueryDTO queryDTO);

    /**
     * 获取当前用户的知识库列表
     *
     * @param queryDTO 查询条件
     * @return 分页结果
     */
    PageResult<KnowledgeBaseInfoDTO> listByCurrentUser(KnowledgeBaseQueryDTO queryDTO);
}
