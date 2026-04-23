package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.*;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.PromptTemplateInfoDTO;
import com.hfusionhub.dto.PromptTemplateSaveDTO;
import com.hfusionhub.dto.PromptTemplateVersionDTO;
import com.hfusionhub.entity.PromptTemplate;
import com.hfusionhub.entity.PromptTemplateVersion;
import com.hfusionhub.mapper.PromptTemplateMapper;
import com.hfusionhub.mapper.PromptTemplateVersionMapper;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;

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

        assertThrows(BusinessException.class, () -> promptTemplateService.publish(3L, 1));
        verify(promptTemplateMapper, never()).update(any(), any());
    }

    @Test
    void publishSnapshotsNewStateAfterStatusChange() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "简洁回答", 1, PromptTemplate.STATUS_DRAFT);
        PromptTemplate afterPublish = owned(3L, 7L, "客服助手", "简洁回答", 2, PromptTemplate.STATUS_PUBLISHED);

        when(promptTemplateMapper.selectById(3L)).thenReturn(template, afterPublish);
        when(promptTemplateMapper.update(isNull(), any(UpdateWrapper.class))).thenReturn(1);

        PromptTemplateInfoDTO result = promptTemplateService.publish(3L, 1);

        assertEquals(PromptTemplate.STATUS_PUBLISHED, result.getStatus());
        assertEquals(2, result.getVersion());
        verify(promptTemplateMapper).update(isNull(), any(UpdateWrapper.class));

        // PUBLISH snapshot AFTER status change (version incremented to v2, status=PUBLISHED)
        ArgumentCaptor<PromptTemplateVersion> vCaptor = ArgumentCaptor.forClass(PromptTemplateVersion.class);
        verify(versionMapper).insert(vCaptor.capture());
        assertEquals(2, vCaptor.getValue().getVersion());
        assertEquals(PromptTemplateVersion.OP_PUBLISH, vCaptor.getValue().getOperation());
        assertEquals(PromptTemplate.STATUS_PUBLISHED, vCaptor.getValue().getStatus());
    }

    @Test
    void publishRejectsWhenVersionMismatched() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "简洁回答", 2, PromptTemplate.STATUS_DRAFT);
        PromptTemplate current = owned(3L, 7L, "客服助手", "已被他人修改", 3, PromptTemplate.STATUS_DRAFT);

        when(promptTemplateMapper.selectById(3L)).thenReturn(template, current);
        when(promptTemplateMapper.update(isNull(), any(UpdateWrapper.class))).thenReturn(0);

        BusinessException ex = assertThrows(BusinessException.class, () -> promptTemplateService.publish(3L, 1));
        assertTrue(ex.getMessage().contains("已被其他操作更新"));
        assertTrue(ex.getMessage().contains("v3"));
        assertEquals(409, ex.getCode());
    }

    @Test
    void unpublishSnapshotsNewStateAfterStatusChange() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "简洁回答", 1, PromptTemplate.STATUS_PUBLISHED);
        PromptTemplate afterUnpublish = owned(3L, 7L, "客服助手", "简洁回答", 2, PromptTemplate.STATUS_DRAFT);

        when(promptTemplateMapper.selectById(3L)).thenReturn(template, afterUnpublish);
        when(promptTemplateMapper.update(isNull(), any(UpdateWrapper.class))).thenReturn(1);

        PromptTemplateInfoDTO result = promptTemplateService.unpublish(3L, 1);

        assertEquals(PromptTemplate.STATUS_DRAFT, result.getStatus());
        assertEquals(2, result.getVersion());
        verify(promptTemplateMapper).update(isNull(), any(UpdateWrapper.class));

        // UNPUBLISH snapshot AFTER status change (version incremented to v2)
        ArgumentCaptor<PromptTemplateVersion> vCaptor = ArgumentCaptor.forClass(PromptTemplateVersion.class);
        verify(versionMapper).insert(vCaptor.capture());
        assertEquals(2, vCaptor.getValue().getVersion());
        assertEquals(PromptTemplateVersion.OP_UNPUBLISH, vCaptor.getValue().getOperation());
        assertEquals(PromptTemplate.STATUS_DRAFT, vCaptor.getValue().getStatus());
    }

    @Test
    void unpublishRejectsWhenVersionMismatched() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "简洁回答", 2, PromptTemplate.STATUS_PUBLISHED);
        PromptTemplate current = owned(3L, 7L, "客服助手", "新内容", 3, PromptTemplate.STATUS_DRAFT);

        when(promptTemplateMapper.selectById(3L)).thenReturn(template, current);
        when(promptTemplateMapper.update(isNull(), any(UpdateWrapper.class))).thenReturn(0);

        BusinessException ex = assertThrows(BusinessException.class, () -> promptTemplateService.unpublish(3L, 1));
        assertTrue(ex.getMessage().contains("已被其他操作更新"));
        assertEquals(409, ex.getCode());
    }

    // ── Update (edit) ───────────────────────────────────────────────

    @Test
    void updateSnapshotsNewStateAfterIncrement() {
        // Current template v2
        PromptTemplate template = owned(3L, 7L, "客服助手", "简洁回答", 2, PromptTemplate.STATUS_DRAFT);
        // After atomic update: v3, DRAFT, new content
        PromptTemplate afterUpdate = owned(3L, 7L, "客服助手", "先给结论", 3, PromptTemplate.STATUS_DRAFT);

        when(promptTemplateMapper.selectById(3L)).thenReturn(template, afterUpdate);
        when(promptTemplateMapper.selectCount(any(LambdaQueryWrapper.class))).thenReturn(0L);
        when(promptTemplateMapper.update(isNull(), any(UpdateWrapper.class))).thenReturn(1);

        PromptTemplateInfoDTO result = promptTemplateService.update(3L, save("客服助手", "先给结论", 2));

        assertEquals(3, result.getVersion());
        assertEquals("先给结论", result.getContent());
        verify(promptTemplateMapper).update(isNull(), any(UpdateWrapper.class));

        // EDIT snapshot AFTER increment: captures NEW state v3
        ArgumentCaptor<PromptTemplateVersion> vCaptor = ArgumentCaptor.forClass(PromptTemplateVersion.class);
        verify(versionMapper).insert(vCaptor.capture());
        assertEquals(3, vCaptor.getValue().getVersion());
        assertEquals(PromptTemplateVersion.OP_EDIT, vCaptor.getValue().getOperation());
        assertEquals("先给结论", vCaptor.getValue().getContent());
    }

    @Test
    void updateDoesNotSnapshotWhenNothingChanged() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "简洁回答", 1, PromptTemplate.STATUS_DRAFT);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);
        when(promptTemplateMapper.selectCount(any(LambdaQueryWrapper.class))).thenReturn(0L);
        when(promptTemplateMapper.update(isNull(), any(UpdateWrapper.class))).thenReturn(1);

        promptTemplateService.update(3L, save("客服助手", "简洁回答", 1));

        verify(versionMapper, never()).insert(any());
    }

    @Test
    void updateRejectsWhenVersionMismatched() {
        // Template was v3 when loaded, but someone already bumped it to v4
        PromptTemplate template = owned(3L, 7L, "客服助手", "v3内容", 3, PromptTemplate.STATUS_DRAFT);
        PromptTemplate current = owned(3L, 7L, "客服助手", "v4内容-被他人修改", 4, PromptTemplate.STATUS_DRAFT);

        when(promptTemplateMapper.selectById(3L)).thenReturn(template, current);
        when(promptTemplateMapper.selectCount(any(LambdaQueryWrapper.class))).thenReturn(0L);
        when(promptTemplateMapper.update(isNull(), any(UpdateWrapper.class))).thenReturn(0);

        BusinessException ex =
                assertThrows(BusinessException.class, () -> promptTemplateService.update(3L, save("客服助手", "我的修改", 3)));
        assertTrue(ex.getMessage().contains("已被其他操作更新"));
        assertTrue(ex.getMessage().contains("v4"));
        assertEquals(409, ex.getCode());
        verify(versionMapper, never()).insert(any());
    }

    @Test
    void updateRejectsWhenExpectedVersionMissing() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "简洁回答", 1, PromptTemplate.STATUS_DRAFT);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);

        BusinessException ex = assertThrows(
                BusinessException.class,
                () -> promptTemplateService.update(3L, save("客服助手", "新内容"))); // no expectedVersion
        assertTrue(
                ex.getMessage().contains("expectedVersion"),
                "Expected error about missing expectedVersion, got: " + ex.getMessage());
        verify(promptTemplateMapper, never()).update(any(), any());
    }

    // ── Rollback ────────────────────────────────────────────────────

    @Test
    void rollbackRestoresContentAndSetsDraft() {
        // Current template at v3
        PromptTemplate template = owned(3L, 7L, "客服助手", "第三次修改", 3, PromptTemplate.STATUS_DRAFT);
        // After atomic rollback: v4, DRAFT, restored content
        PromptTemplate afterRollback = owned(3L, 7L, "原始名称", "第一次创建的内容", 4, PromptTemplate.STATUS_DRAFT);
        afterRollback.setDescription("帮助文档");

        when(promptTemplateMapper.selectById(3L)).thenReturn(template, afterRollback);

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
        when(promptTemplateMapper.update(isNull(), any(UpdateWrapper.class))).thenReturn(1);

        PromptTemplateInfoDTO result = promptTemplateService.rollback(3L, 10L, 3);

        assertEquals("第一次创建的内容", result.getContent());
        assertEquals("原始名称", result.getName());
        assertEquals("帮助文档", result.getDescription());
        assertEquals(PromptTemplate.STATUS_DRAFT, result.getStatus());
        assertEquals(4, result.getVersion()); // v3 → v4
        verify(promptTemplateMapper).update(isNull(), any(UpdateWrapper.class));

        // ROLLBACK snapshot AFTER restore: captures NEW state v4
        ArgumentCaptor<PromptTemplateVersion> vCaptor = ArgumentCaptor.forClass(PromptTemplateVersion.class);
        verify(versionMapper).insert(vCaptor.capture());
        assertEquals(4, vCaptor.getValue().getVersion());
        assertEquals(PromptTemplateVersion.OP_ROLLBACK, vCaptor.getValue().getOperation());
        assertEquals("第一次创建的内容", vCaptor.getValue().getContent());
    }

    @Test
    void rollbackRejectsWhenVersionMismatched() {
        // Current template at v3, but DB is already at v4
        PromptTemplate template = owned(3L, 7L, "客服助手", "v3内容", 3, PromptTemplate.STATUS_DRAFT);
        PromptTemplate current = owned(3L, 7L, "客服助手", "v4内容-冲突", 4, PromptTemplate.STATUS_DRAFT);

        when(promptTemplateMapper.selectById(3L)).thenReturn(template, current);

        PromptTemplateVersion v1 = new PromptTemplateVersion();
        v1.setId(10L);
        v1.setTemplateId(3L);
        v1.setVersion(1);
        v1.setName("原始名称");
        v1.setContent("旧内容");
        v1.setStatus(PromptTemplate.STATUS_DRAFT);
        v1.setOperation(PromptTemplateVersion.OP_CREATE);
        v1.setOperatorId(7L);
        when(versionMapper.selectById(10L)).thenReturn(v1);
        when(promptTemplateMapper.update(isNull(), any(UpdateWrapper.class))).thenReturn(0);

        BusinessException ex = assertThrows(BusinessException.class, () -> promptTemplateService.rollback(3L, 10L, 3));
        assertTrue(ex.getMessage().contains("已被其他操作更新"));
        assertTrue(ex.getMessage().contains("v4"));
        assertEquals(409, ex.getCode());
        verify(versionMapper, never()).insert(any());
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

        assertThrows(BusinessException.class, () -> promptTemplateService.rollback(3L, 5L, 3));
        verify(promptTemplateMapper, never()).update(any(), any());
    }

    @Test
    void rollbackRejectsNonExistentSnapshot() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "内容", 1, PromptTemplate.STATUS_DRAFT);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);
        when(versionMapper.selectById(99L)).thenReturn(null);

        assertThrows(BusinessException.class, () -> promptTemplateService.rollback(3L, 99L, 1));
        verify(promptTemplateMapper, never()).update(any(), any());
    }

    @Test
    void rollbackRejectsSnapshotFromOtherTemplate() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "内容", 1, PromptTemplate.STATUS_DRAFT);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);

        PromptTemplateVersion other = new PromptTemplateVersion();
        other.setId(5L);
        other.setTemplateId(8L); // belongs to template 8, not 3
        when(versionMapper.selectById(5L)).thenReturn(other);

        assertThrows(BusinessException.class, () -> promptTemplateService.rollback(3L, 5L, 1));
        verify(promptTemplateMapper, never()).update(any(), any());
    }

    @Test
    void rollbackRejectsTemplateOwnedByAnotherUser() {
        PromptTemplate template = new PromptTemplate();
        template.setId(3L);
        template.setUserId(8L); // not 7L
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);

        assertThrows(BusinessException.class, () -> promptTemplateService.rollback(3L, 1L, 1));
        verify(promptTemplateMapper, never()).update(any(), any());
    }

    // ── Version history ─────────────────────────────────────────────

    @Test
    void listVersionsReturnsSnapshotsNewestFirst() {
        PromptTemplate template = owned(3L, 7L, "客服助手", "内容", 3, PromptTemplate.STATUS_DRAFT);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);

        PromptTemplateVersion v3 = new PromptTemplateVersion();
        v3.setId(30L);
        v3.setVersion(3);
        v3.setOperation(PromptTemplateVersion.OP_EDIT);
        PromptTemplateVersion v2 = new PromptTemplateVersion();
        v2.setId(20L);
        v2.setVersion(2);
        v2.setOperation(PromptTemplateVersion.OP_EDIT);
        PromptTemplateVersion v1 = new PromptTemplateVersion();
        v1.setId(10L);
        v1.setVersion(1);
        v1.setOperation(PromptTemplateVersion.OP_CREATE);

        when(versionMapper.selectList(any(LambdaQueryWrapper.class))).thenReturn(List.of(v3, v2, v1));

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
        return save(name, content, null);
    }

    private PromptTemplateSaveDTO save(String name, String content, Integer expectedVersion) {
        PromptTemplateSaveDTO dto = new PromptTemplateSaveDTO();
        dto.setName(name);
        dto.setContent(content);
        dto.setExpectedVersion(expectedVersion);
        return dto;
    }
}
