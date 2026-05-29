package com.hfusionhub.service;

import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.dto.BidProjectCreateDTO;
import com.hfusionhub.dto.BidProjectDetailDTO;
import com.hfusionhub.dto.BidProjectInfoDTO;
import com.hfusionhub.dto.BidProjectQueryDTO;

/**
 * 投标项目服务接口（招投标垂直化）
 *
 * @author HFusionHub Team
 */
public interface BidProjectService {

    /**
     * 创建投标项目（初始状态 interpreting）
     */
    BidProjectInfoDTO create(BidProjectCreateDTO createDTO);

    /**
     * 获取项目基本信息
     */
    BidProjectInfoDTO getById(Long id);

    /**
     * 获取项目详情（项目 + 要素 + 评分办法 + 需求清单）
     */
    BidProjectDetailDTO getDetail(Long id);

    /**
     * 分页查询当前用户的投标项目
     */
    PageResult<BidProjectInfoDTO> list(BidProjectQueryDTO queryDTO);

    /**
     * 删除投标项目（软删除）
     */
    void delete(Long id);

    /**
     * 推进项目状态机
     */
    BidProjectInfoDTO updateStatus(Long id, String status);

    /**
     * 触发招标解读：调用 Python 解读工作流，持久化要素/评分办法/需求清单，
     * 低置信需求标记 manual_review。
     */
    BidProjectDetailDTO interpret(Long id);

    /**
     * 更新需求满足状态（用于人工确认/修正需求清单）
     */
    void updateRequirementStatus(Long id, Long requirementId, String status);
}
