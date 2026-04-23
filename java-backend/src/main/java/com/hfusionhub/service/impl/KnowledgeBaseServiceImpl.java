package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.dto.PageResult;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.KnowledgeBaseCreateDTO;
import com.hfusionhub.dto.KnowledgeBaseInfoDTO;
import com.hfusionhub.dto.KnowledgeBaseQueryDTO;
import com.hfusionhub.dto.KnowledgeBaseUpdateDTO;
import com.hfusionhub.entity.Document;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.DeletionService;
import com.hfusionhub.service.KnowledgeBaseService;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/**
 * 知识库服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KnowledgeBaseServiceImpl implements KnowledgeBaseService {

    private static final String KB_DISABLED_DOCUMENT_MESSAGE =
            "\u77e5\u8bc6\u5e93\u5df2\u7981\u7528\uff0c\u542f\u7528\u540e\u53ef\u91cd\u65b0\u5206\u5757";

    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final UserMapper userMapper;
    private final DocumentMapper documentMapper;
    private final JwtUtils jwtUtils;
    private final DeletionService deletionService;

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
        wrapper.eq(KnowledgeBase::getUserId, userId).eq(KnowledgeBase::getName, createDTO.getName());
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
    @Transactional
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
        Integer previousStatus = knowledgeBase.getStatus();
        if (updateDTO.getStatus() != null) {
            if (updateDTO.getStatus() != CommonConstants.KB_STATUS_NORMAL
                    && updateDTO.getStatus() != CommonConstants.KB_STATUS_DISABLED) {
                throw new BusinessException("知识库状态无效");
            }
            knowledgeBase.setStatus(updateDTO.getStatus());
        }

        knowledgeBaseMapper.updateById(knowledgeBase);

        if (previousStatus != null
                && previousStatus == CommonConstants.KB_STATUS_NORMAL
                && knowledgeBase.getStatus() != null
                && knowledgeBase.getStatus() == CommonConstants.KB_STATUS_DISABLED) {
            deletionService.createTask("KB_DISABLE", id);
        }
        if (previousStatus != null
                && previousStatus == CommonConstants.KB_STATUS_DISABLED
                && knowledgeBase.getStatus() != null
                && knowledgeBase.getStatus() == CommonConstants.KB_STATUS_NORMAL) {
            clearKbDisabledDocumentMessage(id);
        }

        log.info("知识库更新成功，id: {}", id);
        return convertToInfoDTO(knowledgeBase);
    }

    private void clearKbDisabledDocumentMessage(Long knowledgeBaseId) {
        documentMapper.update(
                null,
                new LambdaUpdateWrapper<Document>()
                        .eq(Document::getKnowledgeBaseId, knowledgeBaseId)
                        .eq(Document::getDeleted, 0)
                        .eq(Document::getErrorMessage, KB_DISABLED_DOCUMENT_MESSAGE)
                        .set(Document::getErrorMessage, null));
    }

    /**
     * 删除知识库（创建异步删除任务，由调度器执行级联清理）
     *
     * @param id 知识库ID
     */
    @Override
    @Transactional
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

        if (knowledgeBase.getDeleted() != null && knowledgeBase.getDeleted() == 1) {
            throw new BusinessException("知识库已在回收站中");
        }

        // 知识库删除先进入回收站，保留文档、原文件和索引，确保可以完整恢复。
        LocalDateTime recycledAt = LocalDateTime.now();
        int updated =
                knowledgeBaseMapper.markRecycled(id, recycledAt, recycledAt.plusDays(7), knowledgeBase.getStatus());
        if (updated != 1) {
            throw new BusinessException("知识库移入回收站失败");
        }

        log.info("知识库已移入回收站，id: {}", id);
    }

    @Override
    public PageResult<KnowledgeBaseInfoDTO> listRecycleBin(KnowledgeBaseQueryDTO queryDTO) {
        queryDTO.validate();
        Long currentUserId = jwtUtils.getCurrentUserId();
        String name =
                StringUtils.hasText(queryDTO.getName()) ? queryDTO.getName().trim() : null;
        long total = knowledgeBaseMapper.countRecycle(currentUserId, name);
        if (total == 0) {
            return PageResult.of(queryDTO.getPage(), queryDTO.getPageSize(), 0, List.of());
        }
        List<KnowledgeBase> records = knowledgeBaseMapper.selectRecyclePage(
                currentUserId, name, (queryDTO.getPage() - 1) * queryDTO.getPageSize(), queryDTO.getPageSize());
        List<KnowledgeBaseInfoDTO> result =
                records.stream().map(this::convertToInfoDTO).collect(Collectors.toList());
        return PageResult.of(queryDTO.getPage(), queryDTO.getPageSize(), total, result);
    }

    @Override
    @Transactional
    public void restore(Long id) {
        KnowledgeBase knowledgeBase = knowledgeBaseMapper.selectIncludingDeleted(id);
        assertOwnedRecycleBinItem(knowledgeBase);
        if (knowledgeBase.getRecycleExpiresAt() != null
                && knowledgeBase.getRecycleExpiresAt().isBefore(LocalDateTime.now())) {
            throw new BusinessException("该知识库已超过回收站保留期限");
        }

        LambdaQueryWrapper<KnowledgeBase> duplicate = new LambdaQueryWrapper<>();
        duplicate
                .eq(KnowledgeBase::getUserId, jwtUtils.getCurrentUserId())
                .eq(KnowledgeBase::getName, knowledgeBase.getName());
        if (knowledgeBaseMapper.selectCount(duplicate) > 0) {
            throw new BusinessException("已有同名知识库，请先修改现有知识库名称");
        }
        int restoreStatus =
                knowledgeBase.getStatus() != null && knowledgeBase.getStatus() == CommonConstants.KB_STATUS_DISABLED
                        ? CommonConstants.KB_STATUS_DISABLED
                        : CommonConstants.KB_STATUS_NORMAL;
        if (knowledgeBaseMapper.restoreFromRecycle(id, restoreStatus) != 1) {
            throw new BusinessException("恢复知识库失败");
        }
    }

    @Override
    public void purge(Long id) {
        KnowledgeBase knowledgeBase = knowledgeBaseMapper.selectIncludingDeleted(id);
        assertOwnedRecycleBinItem(knowledgeBase);
        deletionService.createTask("KB_PURGE", id);
    }

    private void assertOwnedRecycleBinItem(KnowledgeBase knowledgeBase) {
        if (knowledgeBase == null || knowledgeBase.getDeleted() == null || knowledgeBase.getDeleted() != 1) {
            throw new BusinessException("回收站中不存在该知识库");
        }
        if (!knowledgeBase.getUserId().equals(jwtUtils.getCurrentUserId())) {
            throw new BusinessException("无权操作此知识库");
        }
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
        if (!knowledgeBase.getUserId().equals(jwtUtils.getCurrentUserId())) {
            throw new BusinessException(StatusCode.FORBIDDEN, "无权访问此知识库");
        }
        return convertToInfoDTO(knowledgeBase);
    }

    /**
     * 分页查询知识库列表（所有知识库）
     *
     * @param queryDTO 查询条件
     * @return 分页结果
     */
    @Override
    public PageResult<KnowledgeBaseInfoDTO> list(KnowledgeBaseQueryDTO queryDTO) {
        return listByCurrentUser(queryDTO);
    }

    /**
     * 获取当前用户的知识库列表
     *
     * @param queryDTO 查询条件
     * @return 分页结果
     */
    @Override
    public PageResult<KnowledgeBaseInfoDTO> listByCurrentUser(KnowledgeBaseQueryDTO queryDTO) {
        Long userId = jwtUtils.getCurrentUserId();
        return listInternal(userId, queryDTO);
    }

    /**
     * 内部统一分页查询方法（避免N+1查询）
     *
     * @param userId   用户ID（为null则查询所有）
     * @param queryDTO 查询条件
     * @return 分页结果
     */
    private PageResult<KnowledgeBaseInfoDTO> listInternal(Long userId, KnowledgeBaseQueryDTO queryDTO) {
        queryDTO.validate();

        LambdaQueryWrapper<KnowledgeBase> wrapper = new LambdaQueryWrapper<>();

        // 按用户过滤
        if (userId != null) {
            wrapper.eq(KnowledgeBase::getUserId, userId);
        }

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

        if (result.getRecords().isEmpty()) {
            return PageResult.of(result.getCurrent(), result.getSize(), result.getTotal(), List.of());
        }

        // 批量预加载用户信息（避免N+1）
        List<Long> userIds = result.getRecords().stream()
                .map(KnowledgeBase::getUserId)
                .distinct()
                .collect(Collectors.toList());
        Map<Long, String> usernameMap = Map.of();
        if (!userIds.isEmpty()) {
            List<User> users = userMapper.selectBatchIds(userIds);
            usernameMap = users.stream().collect(java.util.stream.Collectors.toMap(User::getId, User::getUsername));
        }

        // 批量预加载文档数量（避免N+1）
        List<Long> kbIds =
                result.getRecords().stream().map(KnowledgeBase::getId).collect(Collectors.toList());
        Map<Long, Long> docCountMap = Map.of();
        if (!kbIds.isEmpty()) {
            // 使用SQL分组查询获取每个知识库的文档数
            LambdaQueryWrapper<com.hfusionhub.entity.Document> docWrapper = new LambdaQueryWrapper<>();
            docWrapper
                    .in(com.hfusionhub.entity.Document::getKnowledgeBaseId, kbIds)
                    .select(com.hfusionhub.entity.Document::getKnowledgeBaseId);
            List<com.hfusionhub.entity.Document> docs = documentMapper.selectList(docWrapper);
            docCountMap = docs.stream()
                    .collect(java.util.stream.Collectors.groupingBy(
                            com.hfusionhub.entity.Document::getKnowledgeBaseId,
                            java.util.stream.Collectors.counting()));
        }

        // 转换为 DTO（使用预查询数据）
        final Map<Long, String> finalUsernameMap = usernameMap;
        final Map<Long, Long> finalDocCountMap = docCountMap;
        List<KnowledgeBaseInfoDTO> records = result.getRecords().stream()
                .map(kb -> KnowledgeBaseInfoDTO.builder()
                        .id(kb.getId())
                        .name(kb.getName())
                        .description(kb.getDescription())
                        .userId(kb.getUserId())
                        .username(finalUsernameMap.getOrDefault(kb.getUserId(), "unknown"))
                        .status(kb.getStatus())
                        .recycledAt(kb.getRecycledAt())
                        .recycleExpiresAt(kb.getRecycleExpiresAt())
                        .documentCount(
                                finalDocCountMap.getOrDefault(kb.getId(), 0L).intValue())
                        .createdAt(kb.getCreatedAt())
                        .updatedAt(kb.getUpdatedAt())
                        .build())
                .collect(Collectors.toList());

        return PageResult.of(result.getCurrent(), result.getSize(), result.getTotal(), records);
    }

    /**
     * KnowledgeBase 实体转换为 KnowledgeBaseInfoDTO（单条转换，用于getById/create/update）
     *
     * @param knowledgeBase 知识库实体
     * @return 知识库信息DTO
     */
    private KnowledgeBaseInfoDTO convertToInfoDTO(KnowledgeBase knowledgeBase) {
        // 查询创建者用户名
        User user = userMapper.selectById(knowledgeBase.getUserId());
        String username = user != null ? user.getUsername() : "unknown";

        // 查询文档数量
        LambdaQueryWrapper<com.hfusionhub.entity.Document> docWrapper = new LambdaQueryWrapper<>();
        docWrapper.eq(com.hfusionhub.entity.Document::getKnowledgeBaseId, knowledgeBase.getId());
        Long documentCount = knowledgeBase.getDeleted() != null && knowledgeBase.getDeleted() == 1
                ? (long) documentMapper.countByKnowledgeBaseIncludingDeleted(knowledgeBase.getId())
                : documentMapper.selectCount(docWrapper);

        return KnowledgeBaseInfoDTO.builder()
                .id(knowledgeBase.getId())
                .name(knowledgeBase.getName())
                .description(knowledgeBase.getDescription())
                .userId(knowledgeBase.getUserId())
                .username(username)
                .status(knowledgeBase.getStatus())
                .recycledAt(knowledgeBase.getRecycledAt())
                .recycleExpiresAt(knowledgeBase.getRecycleExpiresAt())
                .documentCount(documentCount.intValue())
                .createdAt(knowledgeBase.getCreatedAt())
                .updatedAt(knowledgeBase.getUpdatedAt())
                .build();
    }
}
