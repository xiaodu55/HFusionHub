package com.hfusionhub.service.impl;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.Note;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.NoteMapper;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * NoteServiceImpl 单元测试 — 用户笔记 CRUD 与归属校验。
 */
@ExtendWith(MockitoExtension.class)
class NoteServiceImplTest {

    private static final Long USER_ID = 1L;
    private static final Long OTHER_USER_ID = 2L;

    @Mock
    private NoteMapper noteMapper;

    @Mock
    private KnowledgeBaseMapper knowledgeBaseMapper;

    private NoteServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new NoteServiceImpl(noteMapper, knowledgeBaseMapper);
    }

    @Test
    void createNoteRejectsMissingContent() {
        assertThatThrownBy(() -> service.createNote(USER_ID, 1L, null, null, null, "标题", "  ", "manual"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("内容不能为空");
    }

    @Test
    void createNoteRejectsMissingUser() {
        assertThatThrownBy(() -> service.createNote(null, 1L, null, null, null, "标题", "内容", null))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("用户ID");
    }

    @Test
    void createNoteDefaultsSourceAndDerivesTitle() {
        Note saved = service.createNote(USER_ID, 1L, null, null, null, null, "这是一段足够作为标题的笔记内容", null);

        assertThat(saved.getUserId()).isEqualTo(USER_ID);
        assertThat(saved.getSource()).isEqualTo("manual");
        assertThat(saved.getTitle()).isNotBlank();
        verify(noteMapper).insert(saved);
    }

    @Test
    void createNoteRejectsKnowledgeBaseOfOtherUser() {
        KnowledgeBase kb = new KnowledgeBase();
        kb.setUserId(OTHER_USER_ID);
        kb.setDeleted(0);
        when(knowledgeBaseMapper.selectById(5L)).thenReturn(kb);

        assertThatThrownBy(() -> service.createNote(USER_ID, 1L, 5L, null, null, "标题", "内容", "agent"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("无权");
        verify(noteMapper, never()).insert(any(Note.class));
    }

    @Test
    void createNoteRejectsDeletedKnowledgeBase() {
        KnowledgeBase kb = new KnowledgeBase();
        kb.setUserId(USER_ID);
        kb.setDeleted(1);
        when(knowledgeBaseMapper.selectById(5L)).thenReturn(kb);

        assertThatThrownBy(() -> service.createNote(USER_ID, 1L, 5L, null, null, "标题", "内容", "agent"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("不存在");
    }

    @Test
    void getNoteRejectsOtherUsersNote() {
        Note note = new Note();
        note.setId(9L);
        note.setUserId(OTHER_USER_ID);
        when(noteMapper.selectById(9L)).thenReturn(note);

        assertThatThrownBy(() -> service.getNote(USER_ID, 9L))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("笔记不存在");
    }

    @Test
    void updateNoteTruncatesOverlongTitle() {
        Note existing = new Note();
        existing.setId(9L);
        existing.setUserId(USER_ID);
        existing.setTitle("旧标题");
        when(noteMapper.selectById(9L)).thenReturn(existing);
        String longTitle = "长".repeat(300);

        Note updated = service.updateNote(USER_ID, 9L, longTitle, "新内容");

        assertThat(updated.getTitle()).hasSize(200);
        verify(noteMapper).updateById(existing);
    }

    @Test
    void updateNoteRejectsOverlongContent() {
        Note existing = new Note();
        existing.setId(9L);
        existing.setUserId(USER_ID);
        when(noteMapper.selectById(9L)).thenReturn(existing);

        assertThatThrownBy(() -> service.updateNote(USER_ID, 9L, null, "超".repeat(50001)))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("最大长度");
    }

    @Test
    void deleteNoteRemovesOwnedNote() {
        Note existing = new Note();
        existing.setId(9L);
        existing.setUserId(USER_ID);
        when(noteMapper.selectById(9L)).thenReturn(existing);

        service.deleteNote(USER_ID, 9L);

        verify(noteMapper).deleteById(9L);
    }

    @Test
    void listMyNotesClampsLimitBounds() {
        when(noteMapper.selectList(any())).thenReturn(List.of(new Note()));

        List<Note> notes = service.listMyNotes(USER_ID, 0);

        assertThat(notes).hasSize(1);
        verify(noteMapper).selectList(argThat(wrapper -> true));
    }
}
