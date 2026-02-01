package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.KnowledgeBaseCreateDTO;
import com.hfusionhub.dto.KnowledgeBaseInfoDTO;
import com.hfusionhub.dto.KnowledgeBaseQueryDTO;
import com.hfusionhub.dto.KnowledgeBaseUpdateDTO;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.KnowledgeBaseService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.stream.Collectors;

/**
 * 知识库服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KnowledgeBaseServiceImpl implements KnowledgeBaseService {

    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final UserMapper userMapper;
    private final JwtUtils jwtUtils;

    /**
     * 创建知识库
     *
     * @param createDTO 创建请求
     * @return 知识库信息
     */
    @Override
    public KnowledgeBaseInfoDTO create(KnowledgeBaseCreateDTO createDTO) {
        Long userId = jwtUtils.getCurrentUserId();

        // 检查知识库名称是否已存在（当前用户下）
        LambdaQueryWrapper<KnowledgeBase> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(KnowledgeBase::getUserId, userId)
                .eq(KnowledgeBase::getName, createDTO.getName());
        Long count = knowledgeBaseMapper.selectCount(wrapper);
        if (count > 0) {
            throw new BusinessException(StatusCode.KNOWLEDGE_BASE_EXISTS, "知识库名称已存在");
        }

        // 创建知识库
        KnowledgeBase knowledgeBase = new KnowledgeBase();
        knowledgeBase.setName(createDTO.getName());
        knowledgeBase.setDescription(createDTO.getDescription());
        knowledgeBase.setUserId(userId);
        knowledgeBase.setStatus(0);

        knowledgeBaseMapper.insert(knowledgeBase);

        log.info("知识库创建成功，id: {}, name: {}", knowledgeBase.getId(), knowledgeBase.getName());
        return convertToInfoDTO(knowledgeBase);
    }

    /**
     * 更新知识库
     *
     * @param id        知识库ID
     * @param updateDTO 更新请求
     * @return 知识库信息
     */
    @Override
    public KnowledgeBaseInfoDTO update(Long id, KnowledgeBaseUpdateDTO updateDTO) {
        KnowledgeBase knowledgeBase = knowledgeBaseMapper.selectById(id);
        if (knowledgeBase == null) {
            throw new BusinessException(StatusCode.KNOWLEDGE_BASE_NOT_FOUND, "知识库不存在");
        }

        // 校验权限（只有创建者可以更新）
        Long currentUserId = jwtUtils.getCurrentUserId();
        if (!knowledgeBase.getUserId().equals(currentUserId)) {
            throw new BusinessException(StatusCode.FORBIDDEN, "无权操作此知识库");
        }

        // 更新字段
        if (updateDTO.getName() != null) {
            // 检查名称是否已存在
            LambdaQueryWrapper<KnowledgeBase> wrapper = new LambdaQueryWrapper<>();
            wrapper.eq(KnowledgeBase::getUserId, currentUserId)
                    .eq(KnowledgeBase::getName, updateDTO.getName())
                    .ne(KnowledgeBase::getId, id);
            Long count = knowledgeBaseMapper.selectCount(wrapper);
            if (count > 0) {
                throw new BusinessException(StatusCode.KNOWLEDGE_BASE_EXISTS, "知识库名称已存在");
            }
            knowledgeBase.setName(updateDTO.getName());
        }
        if (updateDTO.getDescription() != null) {
            knowledgeBase.setDescription(updateDTO.getDescription());
        }
        if (updateDTO.getStatus() != null) {
            knowledgeBase.setStatus(updateDTO.getStatus());
        }

        knowledgeBaseMapper.updateById(knowledgeBase);

        log.info("知识库更新成功，id: {}", id);
        return convertToInfoDTO(knowledgeBase);
    }

    /**
     * 删除知识库
     *
     * @param id 知识库ID
     */
    @Override
    public void delete(Long id) {
        KnowledgeBase knowledgeBase = knowledgeBaseMapper.selectById(id);
        if (knowledgeBase == null) {
            throw new BusinessException(StatusCode.KNOWLEDGE_BASE_NOT_FOUND, "知识库不存在");
        }

        // 校验权限（只有创建者可以删除）
        Long currentUserId = jwtUtils.getCurrentUserId();
        if (!knowledgeBase.getUserId().equals(currentUserId)) {
            throw new BusinessException(StatusCode.FORBIDDEN, "无权操作此知识库");
        }

        knowledgeBaseMapper.deleteById(id);

        log.info("知识库删除成功，id: {}", id);
    }

    /**
     * 根据ID获取知识库信息
     *
     * @param id 知识库ID
     * @return 知识库信息
     */
    @Override
    public KnowledgeBaseInfoDTO getById(Long id) {
        KnowledgeBase knowledgeBase = knowledgeBaseMapper.selectById(id);
        if (knowledgeBase == null) {
            throw new BusinessException(StatusCode.KNOWLEDGE_BASE_NOT_FOUND, "知识库不存在");
        }
        return convertToInfoDTO(knowledgeBase);
    }

    /**
     * 分页查询知识库列表
     *
     * @param queryDTO 查询条件
     * @return 分页结果
     */
    @Override
    public PageResult<KnowledgeBaseInfoDTO> list(KnowledgeBaseQueryDTO queryDTO) {
        queryDTO.validate();

        LambdaQueryWrapper<KnowledgeBase> wrapper = new LambdaQueryWrapper<>();

        // 名称模糊查询
        if (StringUtils.hasText(queryDTO.getName())) {
            wrapper.like(KnowledgeBase::getName, queryDTO.getName());
        }

        // 状态查询
        if (queryDTO.getStatus() != null) {
            wrapper.eq(KnowledgeBase::getStatus, queryDTO.getStatus());
        }

        // 排序
        wrapper.orderByDesc(KnowledgeBase::getCreatedAt);

        // 分页查询
        Page<KnowledgeBase> page = new Page<>(queryDTO.getPage(), queryDTO.getPageSize());
        Page<KnowledgeBase> result = knowledgeBaseMapper.selectPage(page, wrapper);

        // 转换为 DTO
        List<KnowledgeBaseInfoDTO> records = result.getRecords().stream()
                .map(this::convertToInfoDTO)
                .collect(Collectors.toList());

        return PageResult.of(result.getCurrent(), result.getSize(), result.getTotal(), records);
    }

    /**
     * 获取当前用户的知识库列表
     *
     * @param queryDTO 查询条件
     * @return 分页结果
     */
    @Override
    public PageResult<KnowledgeBaseInfoDTO> listByCurrentUser(KnowledgeBaseQueryDTO queryDTO) {
        queryDTO.validate();

        Long userId = jwtUtils.getCurrentUserId();

        LambdaQueryWrapper<KnowledgeBase> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(KnowledgeBase::getUserId, userId);

        // 名称模糊查询
        if (StringUtils.hasText(queryDTO.getName())) {
            wrapper.like(KnowledgeBase::getName, queryDTO.getName());
        }

        // 状态查询
        if (queryDTO.getStatus() != null) {
            wrapper.eq(KnowledgeBase::getStatus, queryDTO.getStatus());
        }

        // 排序
        wrapper.orderByDesc(KnowledgeBase::getCreatedAt);

        // 分页查询
        Page<KnowledgeBase> page = new Page<>(queryDTO.getPage(), queryDTO.getPageSize());
        Page<KnowledgeBase> result = knowledgeBaseMapper.selectPage(page, wrapper);

        // 转换为 DTO
        List<KnowledgeBaseInfoDTO> records = result.getRecords().stream()
                .map(this::convertToInfoDTO)
                .collect(Collectors.toList());

        return PageResult.of(result.getCurrent(), result.getSize(), result.getTotal(), records);
    }

    /**
     * KnowledgeBase 实体转换为 KnowledgeBaseInfoDTO
     *
     * @param knowledgeBase 知识库实体
     * @return 知识库信息DTO
     */
    private KnowledgeBaseInfoDTO convertToInfoDTO(KnowledgeBase knowledgeBase) {
        // 查询创建者用户名
        User user = userMapper.selectById(knowledgeBase.getUserId());
        String username = user != null ? user.getUsername() : "unknown";

        return KnowledgeBaseInfoDTO.builder()
                .id(knowledgeBase.getId())
                .name(knowledgeBase.getName())
                .description(knowledgeBase.getDescription())
                .userId(knowledgeBase.getUserId())
                .username(username)
                .status(knowledgeBase.getStatus())
                .documentCount(0) // TODO: 查询文档数量
                .createdAt(knowledgeBase.getCreatedAt())
                .updatedAt(knowledgeBase.getUpdatedAt())
                .build();
    }
}
