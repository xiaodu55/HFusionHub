package com.hfusionhub.service;

import com.hfusionhub.entity.MemoryEntry;
import java.util.List;

public interface MemoryService {

    /** Save a new memory entry (user-scoped). */
    MemoryEntry save(MemoryEntry entry);

    MemoryEntry update(Long id, MemoryEntry entry);

    /** List memories for the current user, optionally filtered by type and conversation. */
    List<MemoryEntry> listByUser(String type, Long conversationId);

    /** Delete a memory entry (owner only). */
    void delete(Long id);

    /** Retrieve relevant memories for a conversation context (for AI consumption). */
    List<MemoryEntry> getRelevantMemories(Long userId, String query, int limit);

    List<MemoryEntry> getRelevantMemories(Long userId, Long knowledgeBaseId, String query, int limit);

    /**
     * Batch-save memory entries for an explicit user (internal-token path used
     * by the Python AI long-term memory consolidation). Invalid or duplicate
     * entries (same user + same content) are skipped. Returns the number saved.
     */
    int saveBatchForUser(Long userId, Long conversationId, Long knowledgeBaseId, List<MemoryEntry> entries);
}
