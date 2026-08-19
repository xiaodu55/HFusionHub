package com.hfusionhub.service;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.dto.DocumentInfoDTO;
import com.hfusionhub.dto.DocumentNameDTO;
import com.hfusionhub.dto.DocumentQueryDTO;
import com.hfusionhub.dto.DocumentUpdateDTO;
import org.springframework.web.multipart.MultipartFile;

/**
 * 文档服务接口
 *
 * @author HFusionHub Team
 */
public interface DocumentService {

    /**
     * 上传文档
     *
     * @param file       文件
     * @param title      文档标题
     * @param kbId       知识库ID
     * @param visibility 可见性等级（general/confidential，空则 general）
     * @return 文档信息
     */
    DocumentInfoDTO upload(MultipartFile file, String title, Long kbId, String visibility);

    /**
     * 从公开网页 URL 创建文档（由 Python AI 抓取并暂存为 markdown）。
     *
     * @param url        公开 HTTPS 网页地址
     * @param title      可选标题（留空则取自网页 title）
     * @param kbId       知识库ID
     * @param visibility 可见性等级：general/confidential（null/空白取缺省 general）
     * @return 文档信息
     */
    DocumentInfoDTO createFromUrl(String url, String title, Long kbId, String visibility);

    /**
     * 更新文档
     *
     * @param id     文档ID
     * @param dto    更新信息
     * @return 文档信息
     */
    DocumentInfoDTO update(Long id, DocumentUpdateDTO dto);

    /**
     * 删除文档
     *
     * @param id 文档ID
     */
    void delete(Long id);

    PageResult<DocumentInfoDTO> listRecycleBin(DocumentQueryDTO queryDTO);

    void restore(Long id);

    void purge(Long id);

    /**
     * 获取文档详情
     *
     * @param id 文档ID
     * @return 文档信息
     */
    DocumentInfoDTO getById(Long id);

    /**
     * 获取文档内容
     *
     * @param id 文档ID
     * @return 文档内容
     */
    String getContent(Long id);

    /**
     * 分页查询文档列表
     *
     * @param queryDTO 查询条件
     * @return 分页结果
     */
    PageResult<DocumentInfoDTO> list(DocumentQueryDTO queryDTO);

    /**
     * 获取知识库下的文档列表
     *
     * @param knowledgeBaseId 知识库ID
     * @param queryDTO        查询条件
     * @return 分页结果
     */
    PageResult<DocumentInfoDTO> listByKnowledgeBase(Long knowledgeBaseId, DocumentQueryDTO queryDTO);

    /**
     * 获取当前用户知识库下的文档列表
     *
     * @param knowledgeBaseId 知识库ID
     * @param queryDTO        查询条件
     * @return 分页结果
     */
    PageResult<DocumentInfoDTO> listByCurrentUser(Long knowledgeBaseId, DocumentQueryDTO queryDTO);

    /**
     * 获取文档名称
     *
     * @param id 文档ID
     * @return 文档名称信息
     */
    DocumentNameDTO getDocumentName(Long id);

    /**
     * 解析文档（触发向量化）
     *
     * @param id    文档ID
     * @param model 嵌入模型（可选）
     */
    void parseDocument(Long id, String model);
}
