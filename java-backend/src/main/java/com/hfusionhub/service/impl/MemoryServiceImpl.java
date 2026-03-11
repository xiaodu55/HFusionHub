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

import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

@Slf4j
@Service
@RequiredArgsConstructor
public class MemoryServiceImpl implements MemoryService {

    private static final List<String> ALLOWED_TYPES = List.of(
            "entity_fact", "conversation_summary", "user_preference");

    private final MemoryEntryMapper memoryEntryMapper;

    @Override
    @Transactional
    public MemoryEntry save(MemoryEntry entry) {
        entry.setUserId(JwtUtils.getCurrentUserId());
        if (entry.getImportance() == null) entry.setImportance(0.5);
        validate(entry);
        memoryEntryMapper.insert(entry);
        return entry;
    }

    @Override
    @Transactional
    public MemoryEntry update(Long id, MemoryEntry update) {
        MemoryEntry existing = requireOwned(id, JwtUtils.getCurrentUserId());
        if (StringUtils.hasText(update.getType())) existing.setType(update.getType());
        if (update.getContent() != null) existing.setContent(update.getContent());
        if (update.getEntities() != null) existing.setEntities(update.getEntities());
        if (update.getImportance() != null) existing.setImportance(update.getImportance());
        if (update.getConversationId() != null) existing.setConversationId(update.getConversationId());
        if (update.getKnowledgeBaseId() != null) existing.setKnowledgeBaseId(update.getKnowledgeBaseId());
        existing.setExpiresAt(update.getExpiresAt());
        validate(existing);
        memoryEntryMapper.updateById(existing);
        return existing;
    }

    @Override
    public List<MemoryEntry> listByUser(String type, Long conversationId) {
        Long userId = JwtUtils.getCurrentUserId();
        return memoryEntryMapper.selectList(new LambdaQueryWrapper<MemoryEntry>()
                .eq(MemoryEntry::getUserId, userId)
                .eq(StringUtils.hasText(type), MemoryEntry::getType, type)
                .eq(conversationId != null, MemoryEntry::getConversationId, conversationId)
                .and(w -> w.isNull(MemoryEntry::getExpiresAt)
                        .or().gt(MemoryEntry::getExpiresAt, LocalDateTime.now()))
                .orderByDesc(MemoryEntry::getImportance)
                .orderByDesc(MemoryEntry::getCreatedAt));
    }

    @Override
    @Transactional
    public void delete(Long id) {
        requireOwned(id, JwtUtils.getCurrentUserId());
        memoryEntryMapper.deleteById(id);
    }

    @Override
    public List<MemoryEntry> getRelevantMemories(Long userId, String query, int limit) {
        return getRelevantMemories(userId, null, query, limit);
    }

    @Override
    public List<MemoryEntry> getRelevantMemories(Long userId, Long knowledgeBaseId, String query, int limit) {
        LambdaQueryWrapper<MemoryEntry> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(MemoryEntry::getUserId, userId)
                .in(MemoryEntry::getType, ALLOWED_TYPES)
                .and(w -> w.isNull(MemoryEntry::getExpiresAt)
                        .or().gt(MemoryEntry::getExpiresAt, LocalDateTime.now()))
                .and(knowledgeBaseId != null, w -> w.isNull(MemoryEntry::getKnowledgeBaseId)
                        .or().eq(MemoryEntry::getKnowledgeBaseId, knowledgeBaseId))
                .orderByDesc(MemoryEntry::getImportance)
                .last("LIMIT 100");
        List<String> terms = Arrays.stream((query == null ? "" : query).toLowerCase(Locale.ROOT)
                        .split("[^a-z0-9\\p{IsHan}]+"))
                .filter(term -> term.length() >= 2).distinct().toList();
        return memoryEntryMapper.selectList(wrapper).stream()
                .sorted((left, right) -> Double.compare(relevance(right, terms), relevance(left, terms)))
                .limit(Math.max(0, Math.min(limit, 20)))
                .toList();
    }

    private MemoryEntry requireOwned(Long id, Long userId) {
        MemoryEntry entry = memoryEntryMapper.selectById(id);
        if (entry == null) throw new BusinessException("Memory does not exist");
        if (!entry.getUserId().equals(userId)) throw new BusinessException("Not allowed to operate this memory");
        return entry;
    }

    private void validate(MemoryEntry entry) {
        if (!StringUtils.hasText(entry.getContent()) || entry.getContent().length() > 4000) {
            throw new BusinessException("Memory content must be 1-4000 characters");
        }
        if (!StringUtils.hasText(entry.getType()) || !ALLOWED_TYPES.contains(entry.getType())) {
            throw new BusinessException("Unsupported memory type");
        }
        if (entry.getImportance() != null && (entry.getImportance() < 0 || entry.getImportance() > 1)) {
            throw new BusinessException("Importance must be between 0 and 1");
        }
        if (entry.getExpiresAt() != null && !entry.getExpiresAt().isAfter(LocalDateTime.now())) {
            throw new BusinessException("Memory expiry must be in the future");
        }
    }

    private double relevance(MemoryEntry entry, List<String> terms) {
        double importance = entry.getImportance() == null ? 0.5 : entry.getImportance();
        if (terms.isEmpty()) return importance;
        String text = entry.getContent() == null ? "" : entry.getContent().toLowerCase(Locale.ROOT);
        return importance + terms.stream().filter(text::contains).count();
    }
}
