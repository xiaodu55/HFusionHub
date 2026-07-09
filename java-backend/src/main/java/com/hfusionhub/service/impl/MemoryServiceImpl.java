package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.MemoryEntry;
import com.hfusionhub.mapper.MemoryEntryMapper;
import com.hfusionhub.service.MemoryService;
import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

@Slf4j
@Service
@RequiredArgsConstructor
public class MemoryServiceImpl implements MemoryService {

    private static final List<String> ALLOWED_TYPES = List.of("entity_fact", "conversation_summary", "user_preference");

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
        // 上限 200 条：按重要性/时间排序后的记忆列表对个人用户已足够，
        // 防止单用户记忆无限增长导致每次全量返回拖慢接口。
        return memoryEntryMapper.selectList(new LambdaQueryWrapper<MemoryEntry>()
                .eq(MemoryEntry::getUserId, userId)
                .eq(StringUtils.hasText(type), MemoryEntry::getType, type)
                .eq(conversationId != null, MemoryEntry::getConversationId, conversationId)
                .and(w -> w.isNull(MemoryEntry::getExpiresAt).or().gt(MemoryEntry::getExpiresAt, LocalDateTime.now()))
                .orderByDesc(MemoryEntry::getImportance)
                .orderByDesc(MemoryEntry::getCreatedAt)
                .last("LIMIT 200"));
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
                .and(w -> w.isNull(MemoryEntry::getExpiresAt).or().gt(MemoryEntry::getExpiresAt, LocalDateTime.now()))
                .and(knowledgeBaseId != null, w -> w.isNull(MemoryEntry::getKnowledgeBaseId)
                        .or()
                        .eq(MemoryEntry::getKnowledgeBaseId, knowledgeBaseId))
                .orderByDesc(MemoryEntry::getImportance)
                .last("LIMIT 100");
        List<String> terms = Arrays.stream(
                        (query == null ? "" : query).toLowerCase(Locale.ROOT).split("[^a-z0-9\\p{IsHan}]+"))
                .filter(term -> term.length() >= 2)
                .distinct()
                .toList();
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

    @Override
    @Transactional
    public int saveBatchForUser(Long userId, Long conversationId, Long knowledgeBaseId, List<MemoryEntry> entries) {
        if (userId == null || userId <= 0) {
            throw new BusinessException("user_id is required for internal memory save");
        }
        if (entries == null || entries.isEmpty()) {
            return 0;
        }
        // 防御性上限：Python 侧已限制单批 20 条，这里兜底 50。
        List<MemoryEntry> bounded = entries.size() > 50 ? entries.subList(0, 50) : entries;

        // 去重：同一用户已有相同 content 的记忆直接跳过（LLM 抽取重复会话时高频出现）。
        List<String> contents = bounded.stream()
                .map(MemoryEntry::getContent)
                .filter(StringUtils::hasText)
                .toList();
        Set<String> existing = contents.isEmpty() ? Set.of()
                : memoryEntryMapper.selectList(new LambdaQueryWrapper<MemoryEntry>()
                                .select(MemoryEntry::getContent)
                                .eq(MemoryEntry::getUserId, userId)
                                .in(MemoryEntry::getContent, contents))
                        .stream()
                        .map(MemoryEntry::getContent)
                        .collect(Collectors.toSet());

        int saved = 0;
        for (MemoryEntry entry : bounded) {
            entry.setUserId(userId);
            if (conversationId != null) entry.setConversationId(conversationId);
            if (knowledgeBaseId != null) entry.setKnowledgeBaseId(knowledgeBaseId);
            if (!StringUtils.hasText(entry.getType())) entry.setType("entity_fact");
            if (entry.getImportance() == null) entry.setImportance(0.5);
            try {
                validate(entry);
            } catch (BusinessException e) {
                log.debug("Skip invalid memory entry for user {}: {}", userId, e.getMessage());
                continue;
            }
            if (existing.contains(entry.getContent())) {
                continue;
            }
            memoryEntryMapper.insert(entry);
            saved++;
        }
        return saved;
    }
}
