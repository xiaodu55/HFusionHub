package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.MemoryEntry;
import com.hfusionhub.mapper.MemoryEntryMapper;
import com.hfusionhub.service.MemoryService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class MemoryServiceImpl implements MemoryService {

    private final MemoryEntryMapper memoryEntryMapper;

    @Override
    @Transactional
    public MemoryEntry save(MemoryEntry entry) {
        Long userId = JwtUtils.getCurrentUserId();
        entry.setUserId(userId);
        if (entry.getImportance() == null) {
            entry.setImportance(0.5);
        }
        memoryEntryMapper.insert(entry);
        return entry;
    }

    @Override
    public List<MemoryEntry> listByUser(String type, Long conversationId) {
        Long userId = JwtUtils.getCurrentUserId();
        LambdaQueryWrapper<MemoryEntry> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(MemoryEntry::getUserId, userId)
               .eq(StringUtils.hasText(type), MemoryEntry::getType, type)
               .eq(conversationId != null, MemoryEntry::getConversationId, conversationId)
               .orderByDesc(MemoryEntry::getImportance)
               .orderByDesc(MemoryEntry::getCreatedAt);
        return memoryEntryMapper.selectList(wrapper);
    }

    @Override
    @Transactional
    public void delete(Long id) {
        Long userId = JwtUtils.getCurrentUserId();
        MemoryEntry entry = memoryEntryMapper.selectById(id);
        if (entry == null) {
            throw new BusinessException("记忆不存在");
        }
        if (!entry.getUserId().equals(userId)) {
            throw new BusinessException("无权删除该记忆");
        }
        memoryEntryMapper.deleteById(id);
    }

    @Override
    public List<MemoryEntry> getRelevantMemories(Long userId, String query, int limit) {
        // Simple keyword-based retrieval of entity facts and summaries.
        // For a full semantic search, delegate to the Python AI service.
        LambdaQueryWrapper<MemoryEntry> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(MemoryEntry::getUserId, userId)
               .in(MemoryEntry::getType, List.of("entity_fact", "user_preference"))
               .orderByDesc(MemoryEntry::getImportance)
               .last("LIMIT " + Math.min(limit, 50));
        return memoryEntryMapper.selectList(wrapper);
    }
}
