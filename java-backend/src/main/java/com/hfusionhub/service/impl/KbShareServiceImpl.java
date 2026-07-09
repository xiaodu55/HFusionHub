package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.KbShareInfoDTO;
import com.hfusionhub.entity.KbShare;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.KbShareMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.KbShareService;
import java.util.List;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 知识库共享服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KbShareServiceImpl implements KbShareService {

    private final KbShareMapper kbShareMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;
    private final UserMapper userMapper;

    /** 合法权限档位（Batch 10 授权矩阵：read 生效读，read_write 生效写） */
    private static final List<String> ALLOWED_PERMISSIONS = List.of("read", "read_write");

    @Override
    @Transactional
    public KbShareInfoDTO share(Long knowledgeBaseId, Long targetUserId, String permission) {
        Long currentUserId = JwtUtils.getCurrentUserId();
        KnowledgeBase kb = knowledgeBaseMapper.selectById(knowledgeBaseId);
        if (kb == null) {
            throw new BusinessException("知识库不存在");
        }
        if (!kb.getUserId().equals(currentUserId)) {
            throw new BusinessException("只有知识库所有者可以共享");
        }
        if (targetUserId == null || targetUserId <= 0) {
            throw new BusinessException("被共享用户不能为空");
        }
        if (targetUserId.equals(currentUserId)) {
            throw new BusinessException("不能共享给自己");
        }
        String effectivePermission = (permission == null || permission.isBlank()) ? "read" : permission.trim();
        if (!ALLOWED_PERMISSIONS.contains(effectivePermission)) {
            throw new BusinessException("非法权限档位: " + effectivePermission);
        }
        User target = userMapper.selectById(targetUserId);
        if (target == null) {
            throw new BusinessException("目标用户不存在");
        }

        KbShare existing = kbShareMapper.selectOne(new LambdaQueryWrapper<KbShare>()
                .eq(KbShare::getKnowledgeBaseId, knowledgeBaseId)
                .eq(KbShare::getSharedUserId, targetUserId));
        if (existing != null) {
            // 重复共享 = 权限档位更新
            if (!effectivePermission.equals(existing.getPermission())) {
                existing.setPermission(effectivePermission);
                kbShareMapper.updateById(existing);
                log.info("知识库 {} 对用户 {} 的权限更新为 {}", knowledgeBaseId, targetUserId, effectivePermission);
            }
            return toDTO(existing);
        }

        KbShare share = new KbShare();
        share.setKnowledgeBaseId(knowledgeBaseId);
        share.setOwnerUserId(currentUserId);
        share.setSharedUserId(targetUserId);
        share.setPermission(effectivePermission);
        kbShareMapper.insert(share);
        log.info("知识库 {} 已共享给用户 {}（{}）", knowledgeBaseId, targetUserId, effectivePermission);
        return toDTO(share);
    }

    @Override
    public String getEffectivePermission(Long userId, Long knowledgeBaseId) {
        if (userId == null || knowledgeBaseId == null) {
            return null;
        }
        KnowledgeBase kb = knowledgeBaseMapper.selectById(knowledgeBaseId);
        if (kb != null && userId.equals(kb.getUserId())) {
            return "owner";
        }
        KbShare share = kbShareMapper.selectOne(new LambdaQueryWrapper<KbShare>()
                .eq(KbShare::getKnowledgeBaseId, knowledgeBaseId)
                .eq(KbShare::getSharedUserId, userId));
        return share == null ? null : share.getPermission();
    }

    @Override
    public List<KbShareInfoDTO> listShares(Long knowledgeBaseId) {
        Long currentUserId = JwtUtils.getCurrentUserId();
        KnowledgeBase kb = knowledgeBaseMapper.selectById(knowledgeBaseId);
        if (kb == null || !kb.getUserId().equals(currentUserId)) {
            throw new BusinessException("无权查看该知识库的共享记录");
        }
        return kbShareMapper
                .selectList(new LambdaQueryWrapper<KbShare>()
                        .eq(KbShare::getKnowledgeBaseId, knowledgeBaseId)
                        .orderByDesc(KbShare::getCreatedAt))
                .stream()
                .map(this::toDTO)
                .collect(Collectors.toList());
    }

    @Override
    public List<KbShareInfoDTO> listSharedToMe() {
        Long currentUserId = JwtUtils.getCurrentUserId();
        return kbShareMapper
                .selectList(new LambdaQueryWrapper<KbShare>()
                        .eq(KbShare::getSharedUserId, currentUserId)
                        .orderByDesc(KbShare::getCreatedAt))
                .stream()
                .map(this::toDTO)
                .collect(Collectors.toList());
    }

    @Override
    @Transactional
    public void revoke(Long knowledgeBaseId, Long shareId) {
        Long currentUserId = JwtUtils.getCurrentUserId();
        KnowledgeBase kb = knowledgeBaseMapper.selectById(knowledgeBaseId);
        if (kb == null || !kb.getUserId().equals(currentUserId)) {
            throw new BusinessException("无权撤销该共享");
        }
        kbShareMapper.deleteById(shareId);
    }

    @Override
    public boolean canRead(Long userId, Long knowledgeBaseId) {
        if (userId == null || knowledgeBaseId == null) {
            return false;
        }
        KnowledgeBase kb = knowledgeBaseMapper.selectById(knowledgeBaseId);
        if (kb != null && userId.equals(kb.getUserId())) {
            return true;
        }
        Long count = kbShareMapper.selectCount(new LambdaQueryWrapper<KbShare>()
                .eq(KbShare::getKnowledgeBaseId, knowledgeBaseId)
                .eq(KbShare::getSharedUserId, userId));
        return count != null && count > 0;
    }

    private KbShareInfoDTO toDTO(KbShare share) {
        KbShareInfoDTO dto = new KbShareInfoDTO();
        dto.setId(share.getId());
        dto.setKnowledgeBaseId(share.getKnowledgeBaseId());
        dto.setPermission(share.getPermission());
        dto.setOwnerUserId(share.getOwnerUserId());
        dto.setSharedUserId(share.getSharedUserId());
        dto.setCreatedAt(share.getCreatedAt());
        KnowledgeBase kb = knowledgeBaseMapper.selectById(share.getKnowledgeBaseId());
        dto.setKnowledgeBaseName(kb == null ? null : kb.getName());
        User owner = userMapper.selectById(share.getOwnerUserId());
        dto.setOwnerUsername(owner == null ? null : owner.getUsername());
        User shared = userMapper.selectById(share.getSharedUserId());
        dto.setSharedUsername(shared == null ? null : shared.getUsername());
        return dto;
    }
}
