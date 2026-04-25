package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.Note;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.NoteMapper;
import com.hfusionhub.service.NoteService;
import java.util.List;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/**
 * 用户笔记服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class NoteServiceImpl implements NoteService {

    private static final int MAX_TITLE_LENGTH = 200;
    private static final int MAX_CONTENT_LENGTH = 50000;

    private final NoteMapper noteMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;

    @Override
    @Transactional
    public Note createNote(
            Long userId,
            Long tenantId,
            Long knowledgeBaseId,
            Long conversationId,
            Long messageId,
            String title,
            String content,
            String source) {
        if (userId == null || userId <= 0) {
            throw new BusinessException("笔记缺少用户ID");
        }
        if (!StringUtils.hasText(content)) {
            throw new BusinessException("笔记内容不能为空");
        }
        if (content.length() > MAX_CONTENT_LENGTH) {
            throw new BusinessException("笔记内容超过最大长度 " + MAX_CONTENT_LENGTH);
        }
        // 防御纵深：若指定知识库，校验其存在且属于该用户（Agent 端已校验，此处兜底）。
        if (knowledgeBaseId != null && knowledgeBaseId > 0) {
            KnowledgeBase kb = knowledgeBaseMapper.selectById(knowledgeBaseId);
            if (kb == null || kb.getDeleted() != null && kb.getDeleted() == 1) {
                throw new BusinessException("关联的知识库不存在");
            }
            if (!userId.equals(kb.getUserId())) {
                throw new BusinessException("无权向该知识库写入笔记");
            }
        }

        Note note = new Note();
        note.setUserId(userId);
        note.setTenantId(tenantId);
        note.setKnowledgeBaseId(knowledgeBaseId != null && knowledgeBaseId > 0 ? knowledgeBaseId : null);
        note.setConversationId(conversationId);
        note.setMessageId(messageId);
        note.setTitle(buildTitle(title, content));
        note.setContent(content);
        note.setSource(StringUtils.hasText(source) ? source : "manual");
        noteMapper.insert(note);
        log.info("Note created: id={} userId={} source={}", note.getId(), userId, note.getSource());
        return note;
    }

    @Override
    public List<Note> listMyNotes(Long userId, int limit) {
        int safeLimit = Math.max(1, Math.min(limit <= 0 ? 100 : limit, 500));
        return noteMapper.selectList(new LambdaQueryWrapper<Note>()
                .eq(Note::getUserId, userId)
                .orderByDesc(Note::getId)
                .last("LIMIT " + safeLimit));
    }

    @Override
    public Note getNote(Long userId, Long noteId) {
        Note note = noteMapper.selectById(noteId);
        if (note == null || !userId.equals(note.getUserId())) {
            throw new BusinessException("笔记不存在");
        }
        return note;
    }

    @Override
    @Transactional
    public Note updateNote(Long userId, Long noteId, String title, String content) {
        Note existing = getNote(userId, noteId);
        if (StringUtils.hasText(title)) {
            existing.setTitle(title.length() > MAX_TITLE_LENGTH ? title.substring(0, MAX_TITLE_LENGTH) : title);
        }
        if (content != null) {
            if (content.length() > MAX_CONTENT_LENGTH) {
                throw new BusinessException("笔记内容超过最大长度 " + MAX_CONTENT_LENGTH);
            }
            existing.setContent(content);
            if (!StringUtils.hasText(existing.getTitle())) {
                existing.setTitle(buildTitle(null, content));
            }
        }
        noteMapper.updateById(existing);
        return existing;
    }

    @Override
    @Transactional
    public void deleteNote(Long userId, Long noteId) {
        Note existing = getNote(userId, noteId);
        noteMapper.deleteById(existing.getId());
        log.info("Note deleted: id={} userId={}", noteId, userId);
    }

    private static String buildTitle(String title, String content) {
        if (StringUtils.hasText(title)) {
            return title.length() > MAX_TITLE_LENGTH ? title.substring(0, MAX_TITLE_LENGTH) : title;
        }
        String plain = content.replaceAll("(?s)#+\\s*", "").replaceAll("\\s+", " ").trim();
        if (plain.length() > 30) {
            plain = plain.substring(0, 30) + "…";
        }
        return StringUtils.hasText(plain) ? plain : "笔记";
    }
}
