package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.PromptTemplateInfoDTO;
import com.hfusionhub.dto.PromptTemplateSaveDTO;
import com.hfusionhub.dto.PromptTemplateVersionDTO;
import com.hfusionhub.entity.PromptTemplate;
import com.hfusionhub.entity.PromptTemplateVersion;
import com.hfusionhub.mapper.PromptTemplateMapper;
import com.hfusionhub.mapper.PromptTemplateVersionMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class PromptTemplateServiceImplTest {

    @Mock
    private PromptTemplateMapper promptTemplateMapper;

    @Mock
    private PromptTemplateVersionMapper versionMapper;

    @InjectMocks
    private PromptTemplateServiceImpl promptTemplateService;

    private MockedStatic<JwtUtils> jwtUtils;

    @BeforeEach
    void setUp() {
        jwtUtils = org.mockito.Mockito.mockStatic(JwtUtils.class);
        jwtUtils.when(JwtUtils::getCurrentUserId).thenReturn(7L);
    }

    @AfterEach
    void tearDown() {
        jwtUtils.close();
    }

    // ── Create ──────────────────────────────────────────────────────

    @Test
    void createMakesAUserScopedDraftAtVersionOne() {
        when(promptTemplateMapper.selectCount(any(LambdaQueryWrapper.class))).thenReturn(0L);
        when(promptTemplateMapper.insert(any(PromptTemplate.class))).thenAnswer(invocation -> {
            invocation.getArgument(0, PromptTemplate.class).setId(19L);
            return 1;
        });

        PromptTemplateInfoDTO result = promptTemplateService.create(save("客服助手", "简洁回答"));

        ArgumentCaptor<PromptTemplate> captor = ArgumentCaptor.forClass(PromptTemplate.class);
        verify(promptTemplateMapper).insert(captor.capture());
        assertEquals(7L, captor.getValue().getUserId());
        assertEquals(PromptTemplate.STATUS_DRAFT, captor.getValue().getStatus());
        assertEquals(1, captor.getValue().getVersion());
        assertEquals(19L, result.getId());

        // Snapshot AFTER insert: v1, CREATE, captures the new state
        ArgumentCaptor<PromptTemplateVersion> vCaptor = ArgumentCaptor.forClass(PromptTemplateVersion.class);
        verify(versionMapper).insert(vCaptor.capture());
        assertEquals(19L, vCaptor.getValue().getTemplateId());
        assertEquals(1, vCaptor.getValue().getVersion());
        assertEquals(PromptTemplateVersion.OP_CREATE, vCaptor.getValue().getOperation());
        assertEquals("客服助手", vCaptor.getValue().getName());
        assertEquals("简洁回答", vCaptor.getValue().getContent());
    }

    // ── Publish / Unpublish ─────────────────────────────────────────

    @Test
    void publishRejectsTemplatesOwnedByAnotherUser() {
        PromptTemplate template = new PromptTemplate();
        template.setId(3L);
        template.setUserId(8L);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);

        assertThrows(BusinessException.class, () -> promptTemplateService.publish(3L));
    }

    @Test
    void publishSnapshotsNewStateAfterStatusChange() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "简洁回答", 1, PromptTemplate.STATUS_DRAFT);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);

        PromptTemplateInfoDTO result = promptTemplateService.publish(3L);

        assertEquals(PromptTemplate.STATUS_PUBLISHED, result.getStatus());
        verify(promptTemplateMapper).updateById(template);

        // PUBLISH snapshot AFTER status change (same version v1, status=PUBLISHED)
        ArgumentCaptor<PromptTemplateVersion> vCaptor = ArgumentCaptor.forClass(PromptTemplateVersion.class);
        verify(versionMapper).insert(vCaptor.capture());
        assertEquals(1, vCaptor.getValue().getVersion());
        assertEquals(PromptTemplateVersion.OP_PUBLISH, vCaptor.getValue().getOperation());
        assertEquals(PromptTemplate.STATUS_PUBLISHED, vCaptor.getValue().getStatus());
    }

    @Test
    void unpublishSnapshotsNewStateAfterStatusChange() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "简洁回答", 1, PromptTemplate.STATUS_PUBLISHED);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);

        promptTemplateService.unpublish(3L);

        ArgumentCaptor<PromptTemplateVersion> vCaptor = ArgumentCaptor.forClass(PromptTemplateVersion.class);
        verify(versionMapper).insert(vCaptor.capture());
        assertEquals(PromptTemplateVersion.OP_UNPUBLISH, vCaptor.getValue().getOperation());
        assertEquals(PromptTemplate.STATUS_DRAFT, vCaptor.getValue().getStatus());
    }

    // ── Update (edit) ───────────────────────────────────────────────

    @Test
    void updateSnapshotsNewStateAfterIncrement() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "简洁回答", 2, PromptTemplate.STATUS_DRAFT);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);
        when(promptTemplateMapper.selectCount(any(LambdaQueryWrapper.class))).thenReturn(0L);

        PromptTemplateInfoDTO result = promptTemplateService.update(3L, save("客服助手", "先给结论"));

        assertEquals(3, result.getVersion());
        assertEquals("先给结论", result.getContent());

        // EDIT snapshot AFTER increment: captures NEW state v3
        ArgumentCaptor<PromptTemplateVersion> vCaptor = ArgumentCaptor.forClass(PromptTemplateVersion.class);
        verify(versionMapper).insert(vCaptor.capture());
        assertEquals(3, vCaptor.getValue().getVersion());                // NEW version
        assertEquals(PromptTemplateVersion.OP_EDIT, vCaptor.getValue().getOperation());
        assertEquals("先给结论", vCaptor.getValue().getContent());       // NEW content
    }

    @Test
    void updateDoesNotSnapshotWhenNothingChanged() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "简洁回答", 1, PromptTemplate.STATUS_DRAFT);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);
        when(promptTemplateMapper.selectCount(any(LambdaQueryWrapper.class))).thenReturn(0L);

        promptTemplateService.update(3L, save("客服助手", "简洁回答"));

        verify(versionMapper, never()).insert(any());
    }

    // ── Rollback ────────────────────────────────────────────────────

    @Test
    void rollbackRestoresContentAndSetsDraft() {
        // Current template at v3
        PromptTemplate template = owned(3L, 7L, "客服助手", "第三次修改", 3, PromptTemplate.STATUS_DRAFT);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);

        // Target snapshot id=10, v1
        PromptTemplateVersion v1 = new PromptTemplateVersion();
        v1.setId(10L);
        v1.setTemplateId(3L);
        v1.setVersion(1);
        v1.setName("原始名称");
        v1.setDescription("帮助文档");
        v1.setContent("第一次创建的内容");
        v1.setStatus(PromptTemplate.STATUS_DRAFT);
        v1.setOperation(PromptTemplateVersion.OP_CREATE);
        v1.setOperatorId(7L);
        when(versionMapper.selectById(10L)).thenReturn(v1);
        when(promptTemplateMapper.selectCount(any(LambdaQueryWrapper.class))).thenReturn(0L);

        PromptTemplateInfoDTO result = promptTemplateService.rollback(3L, 10L);

        assertEquals("第一次创建的内容", result.getContent());
        assertEquals("原始名称", result.getName());
        assertEquals("帮助文档", result.getDescription());
        assertEquals(PromptTemplate.STATUS_DRAFT, result.getStatus());
        assertEquals(4, result.getVersion()); // v3 → v4

        // ROLLBACK snapshot AFTER restore: captures NEW state v4
        ArgumentCaptor<PromptTemplateVersion> vCaptor = ArgumentCaptor.forClass(PromptTemplateVersion.class);
        verify(versionMapper).insert(vCaptor.capture());
        assertEquals(4, vCaptor.getValue().getVersion());
        assertEquals(PromptTemplateVersion.OP_ROLLBACK, vCaptor.getValue().getOperation());
        assertEquals("第一次创建的内容", vCaptor.getValue().getContent());
    }

    @Test
    void rollbackChecksNameUniqueness() {
        PromptTemplate template = owned(3L, 7L, "当前名称", "当前内容", 3, PromptTemplate.STATUS_DRAFT);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);

        PromptTemplateVersion v1 = new PromptTemplateVersion();
        v1.setId(5L);
        v1.setTemplateId(3L);
        v1.setVersion(1);
        v1.setName("客服助手"); // different from current, might be taken
        v1.setContent("旧内容");
        v1.setStatus(PromptTemplate.STATUS_DRAFT);
        v1.setOperation(PromptTemplateVersion.OP_CREATE);
        v1.setOperatorId(7L);
        when(versionMapper.selectById(5L)).thenReturn(v1);

        // Another template already uses the old name
        when(promptTemplateMapper.selectCount(any(LambdaQueryWrapper.class))).thenReturn(1L);

        assertThrows(BusinessException.class, () -> promptTemplateService.rollback(3L, 5L));
    }

    @Test
    void rollbackRejectsNonExistentSnapshot() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "内容", 1, PromptTemplate.STATUS_DRAFT);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);
        when(versionMapper.selectById(99L)).thenReturn(null);

        assertThrows(BusinessException.class, () -> promptTemplateService.rollback(3L, 99L));
    }

    @Test
    void rollbackRejectsSnapshotFromOtherTemplate() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "内容", 1, PromptTemplate.STATUS_DRAFT);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);

        PromptTemplateVersion other = new PromptTemplateVersion();
        other.setId(5L);
        other.setTemplateId(8L); // belongs to template 8, not 3
        when(versionMapper.selectById(5L)).thenReturn(other);

        assertThrows(BusinessException.class, () -> promptTemplateService.rollback(3L, 5L));
    }

    @Test
    void rollbackRejectsTemplateOwnedByAnotherUser() {
        PromptTemplate template = new PromptTemplate();
        template.setId(3L);
        template.setUserId(8L); // not 7L
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);

        assertThrows(BusinessException.class, () -> promptTemplateService.rollback(3L, 1L));
    }

    // ── Version history ─────────────────────────────────────────────

    @Test
    void listVersionsReturnsSnapshotsNewestFirst() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "内容", 3, PromptTemplate.STATUS_DRAFT);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);

        PromptTemplateVersion v3 = new PromptTemplateVersion();
        v3.setId(30L); v3.setVersion(3); v3.setOperation(PromptTemplateVersion.OP_EDIT);
        PromptTemplateVersion v2 = new PromptTemplateVersion();
        v2.setId(20L); v2.setVersion(2); v2.setOperation(PromptTemplateVersion.OP_EDIT);
        PromptTemplateVersion v1 = new PromptTemplateVersion();
        v1.setId(10L); v1.setVersion(1); v1.setOperation(PromptTemplateVersion.OP_CREATE);

        when(versionMapper.selectList(any(LambdaQueryWrapper.class)))
                .thenReturn(List.of(v3, v2, v1));

        List<PromptTemplateVersionDTO> versions = promptTemplateService.listVersions(3L);

        assertEquals(3, versions.size());
        assertEquals(3, versions.get(0).getVersion());
        assertEquals(2, versions.get(1).getVersion());
        assertEquals(1, versions.get(2).getVersion());
    }

    // ── helpers ─────────────────────────────────────────────────────

    private PromptTemplate owned(Long id, Long userId, String name, String content, int version, String status) {
        PromptTemplate t = new PromptTemplate();
        t.setId(id);
        t.setUserId(userId);
        t.setName(name);
        t.setContent(content);
        t.setVersion(version);
        t.setStatus(status);
        return t;
    }

    private PromptTemplateSaveDTO save(String name, String content) {
        PromptTemplateSaveDTO dto = new PromptTemplateSaveDTO();
        dto.setName(name);
        dto.setContent(content);
        return dto;
    }
}
