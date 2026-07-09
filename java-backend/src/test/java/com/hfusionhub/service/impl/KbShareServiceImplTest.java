package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.KbShareInfoDTO;
import com.hfusionhub.entity.KbShare;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.KbShareMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.UserMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class KbShareServiceImplTest {

    @Mock
    private KbShareMapper kbShareMapper;

    @Mock
    private KnowledgeBaseMapper knowledgeBaseMapper;

    @Mock
    private UserMapper userMapper;

    @InjectMocks
    private KbShareServiceImpl kbShareService;

    private MockedStatic<JwtUtils> jwtUtilsMock;

    @BeforeEach
    void setUp() {
        jwtUtilsMock = mockStatic(JwtUtils.class);
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);
    }

    @AfterEach
    void tearDown() {
        jwtUtilsMock.close();
    }

    private KnowledgeBase ownedKb() {
        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(10L);
        kb.setUserId(1L);
        return kb;
    }

    private User targetUser() {
        User user = new User();
        user.setId(2L);
        user.setUsername("alice");
        return user;
    }

    @Test
    void shareRejectsNonOwner() {
        KnowledgeBase foreign = new KnowledgeBase();
        foreign.setId(10L);
        foreign.setUserId(2L);
        when(knowledgeBaseMapper.selectById(10L)).thenReturn(foreign);

        assertThrows(BusinessException.class, () -> kbShareService.share(10L, 2L, "read"));
    }

    @Test
    void shareRejectsSelfShare() {
        when(knowledgeBaseMapper.selectById(10L)).thenReturn(ownedKb());

        assertThrows(BusinessException.class, () -> kbShareService.share(10L, 1L, "read"));
    }

    @Test
    void shareCreatesReadOnlyShare() {
        when(knowledgeBaseMapper.selectById(10L)).thenReturn(ownedKb());
        when(userMapper.selectById(2L)).thenReturn(targetUser());
        when(kbShareMapper.selectOne(any())).thenReturn(null);
        when(kbShareMapper.insert(any(KbShare.class))).thenReturn(1);

        KbShareInfoDTO result = kbShareService.share(10L, 2L, "read");

        assertEquals("read", result.getPermission());
        assertEquals(2L, result.getSharedUserId());
        verify(kbShareMapper).insert(any(KbShare.class));
    }

    @Test
    void canReadReturnsTrueForOwner() {
        when(knowledgeBaseMapper.selectById(10L)).thenReturn(ownedKb());

        assertTrue(kbShareService.canRead(1L, 10L));
        verify(kbShareMapper, never()).selectCount(any());
    }

    @Test
    void canReadReturnsTrueForSharedUser() {
        KnowledgeBase foreign = new KnowledgeBase();
        foreign.setId(10L);
        foreign.setUserId(9L);
        when(knowledgeBaseMapper.selectById(10L)).thenReturn(foreign);
        when(kbShareMapper.selectCount(any())).thenReturn(1L);

        assertTrue(kbShareService.canRead(2L, 10L));
    }

    @Test
    void canReadReturnsFalseForStranger() {
        KnowledgeBase foreign = new KnowledgeBase();
        foreign.setId(10L);
        foreign.setUserId(9L);
        when(knowledgeBaseMapper.selectById(10L)).thenReturn(foreign);
        when(kbShareMapper.selectCount(any())).thenReturn(0L);

        assertFalse(kbShareService.canRead(2L, 10L));
    }
}
