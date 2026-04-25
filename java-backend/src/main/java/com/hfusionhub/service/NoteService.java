package com.hfusionhub.service;

import com.hfusionhub.entity.Note;
import java.util.List;

/**
 * 用户笔记服务
 *
 * @author HFusionHub Team
 */
public interface NoteService {

    /**
     * 保存笔记（Agent write_note 内部回调 / 用户手动创建共用）。
     * userId 必填；knowledgeBaseId 若提供则校验其存在且属于该用户。
     */
    Note createNote(
            Long userId,
            Long tenantId,
            Long knowledgeBaseId,
            Long conversationId,
            Long messageId,
            String title,
            String content,
            String source);

    /** 当前用户的笔记列表（最新在前）。 */
    List<Note> listMyNotes(Long userId, int limit);

    /** 查询笔记（校验归属）。 */
    Note getNote(Long userId, Long noteId);

    /** 更新笔记标题/内容（校验归属）。 */
    Note updateNote(Long userId, Long noteId, String title, String content);

    /** 逻辑删除笔记（校验归属）。 */
    void deleteNote(Long userId, Long noteId);
}
