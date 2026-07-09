package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.when;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.KbShare;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.KbShareMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.impl.KbShareServiceImpl;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;

/**
 * Batch 10 资源级授权矩阵测试：kb_share 的 read / read_write 档位生效。
 */
class KbSharePermissionMatrixTest {

    private KbShareMapper kbShareMapper;
    private KnowledgeBaseMapper knowledgeBaseMapper;
    private UserMapper userMapper;
    private KbShareServiceImpl service;
    private MockedStatic<JwtUtils> jwtUtilsMock;

    @BeforeEach
    void setUp() {
        kbShareMapper = mock(KbShareMapper.class);
        knowledgeBaseMapper = mock(KnowledgeBaseMapper.class);
        userMapper = mock(UserMapper.class);
        service = new KbShareServiceImpl(kbShareMapper, knowledgeBaseMapper, userMapper);
        jwtUtilsMock = mockStatic(JwtUtils.class);
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);
    }

    @AfterEach
    void tearDown() {
        jwtUtilsMock.close();
    }

    private KnowledgeBase kb(long ownerId) {
        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(10L);
        kb.setUserId(ownerId);
        return kb;
    }

    // ── share：档位校验与更新 ──────────────────────────────────────────

    @Test
    void shareRejectsInvalidPermission() {
        when(knowledgeBaseMapper.selectById(10L)).thenReturn(kb(1L));
        assertThrows(BusinessException.class,
                () -> service.share(10L, 2L, "admin"));
    }

    @Test
    void shareAcceptsReadWritePermission() {
        when(knowledgeBaseMapper.selectById(10L)).thenReturn(kb(1L));
        when(userMapper.selectById(2L)).thenReturn(new com.hfusionhub.entity.User());
        when(kbShareMapper.selectOne(any())).thenReturn(null);

        KbShare share = new KbShare();
        share.setId(99L);
        share.setKnowledgeBaseId(10L);
        share.setOwnerUserId(1L);
        share.setSharedUserId(2L);
        share.setPermission("read_write");
        when(kbShareMapper.insert(any(KbShare.class))).thenReturn(1);

        var dto = service.share(10L, 2L, "read_write");
        assertEquals("read_write", dto.getPermission());
    }

    // ── getEffectivePermission：授权矩阵 ──────────────────────────────

    @Test
    void ownerHasOwnerPermission() {
        when(knowledgeBaseMapper.selectById(10L)).thenReturn(kb(1L));
        assertEquals("owner", service.getEffectivePermission(1L, 10L));
    }

    @Test
    void sharedUserGetsSharePermission() {
        when(knowledgeBaseMapper.selectById(10L)).thenReturn(kb(1L));
        KbShare share = new KbShare();
        share.setPermission("read_write");
        when(kbShareMapper.selectOne(any())).thenReturn(share);
        assertEquals("read_write", service.getEffectivePermission(2L, 10L));
    }

    @Test
    void strangerGetsNull() {
        when(knowledgeBaseMapper.selectById(10L)).thenReturn(kb(1L));
        when(kbShareMapper.selectOne(any())).thenReturn(null);
        assertNull(service.getEffectivePermission(3L, 10L));
    }

    @Test
    void nullArgumentsReturnNull() {
        assertNull(service.getEffectivePermission(null, 10L));
        assertNull(service.getEffectivePermission(1L, null));
    }
}
