package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.DocumentMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.service.DeletionService;
import java.time.LocalDateTime;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class KnowledgeBaseServiceImplTest {

    @Mock
    private KnowledgeBaseMapper knowledgeBaseMapper;

    @Mock
    private UserMapper userMapper;

    @Mock
    private DocumentMapper documentMapper;

    @Mock
    private JwtUtils jwtUtils;

    @Mock
    private DeletionService deletionService;

    @Mock
    private com.hfusionhub.cache.HotReadCacheService hotReadCache;

    @InjectMocks
    private KnowledgeBaseServiceImpl knowledgeBaseService;

    private MockedStatic<JwtUtils> jwtUtilsMock;

    @BeforeEach
    void setUp() {
        jwtUtilsMock = org.mockito.Mockito.mockStatic(JwtUtils.class);
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(7L);
    }

    @AfterEach
    void tearDown() {
        jwtUtilsMock.close();
    }

    @Test
    void deleteMovesKnowledgeBaseToRecycleBinWithoutCascadeTask() {
        KnowledgeBase knowledgeBase = knowledgeBase(42L, 7L, 0, 0);
        when(knowledgeBaseMapper.selectById(42L)).thenReturn(knowledgeBase);
        when(knowledgeBaseMapper.markRecycled(eq(42L), any(LocalDateTime.class), any(LocalDateTime.class), eq(0)))
                .thenReturn(1);

        knowledgeBaseService.delete(42L);

        verify(knowledgeBaseMapper).markRecycled(eq(42L), any(LocalDateTime.class), any(LocalDateTime.class), eq(0));
        verify(deletionService, never()).createTask(anyString(), anyLong());
    }

    @Test
    void restoreKeepsDisabledStatus() {
        KnowledgeBase knowledgeBase = knowledgeBase(42L, 7L, 1, 1);
        knowledgeBase.setRecycledAt(LocalDateTime.now().minusHours(1));
        knowledgeBase.setRecycleExpiresAt(LocalDateTime.now().plusDays(6));
        when(knowledgeBaseMapper.selectIncludingDeleted(42L)).thenReturn(knowledgeBase);
        when(knowledgeBaseMapper.selectCount(any())).thenReturn(0L);
        when(knowledgeBaseMapper.restoreFromRecycle(42L, 1)).thenReturn(1);

        assertDoesNotThrow(() -> knowledgeBaseService.restore(42L));

        verify(knowledgeBaseMapper).restoreFromRecycle(42L, 1);
    }

    @Test
    void purgeCreatesPermanentDeleteTaskForOwnedRecycleEntry() {
        KnowledgeBase knowledgeBase = knowledgeBase(42L, 7L, 1, 0);
        when(knowledgeBaseMapper.selectIncludingDeleted(42L)).thenReturn(knowledgeBase);

        knowledgeBaseService.purge(42L);

        verify(deletionService).createTask("KB_PURGE", 42L);
    }

    @Test
    void restoreRejectsRecycleEntryOwnedByAnotherUser() {
        when(knowledgeBaseMapper.selectIncludingDeleted(42L)).thenReturn(knowledgeBase(42L, 8L, 1, 0));

        assertThrows(BusinessException.class, () -> knowledgeBaseService.restore(42L));
        verify(knowledgeBaseMapper, never()).restoreFromRecycle(anyLong(), any());
    }

    private KnowledgeBase knowledgeBase(Long id, Long userId, int deleted, int status) {
        KnowledgeBase knowledgeBase = new KnowledgeBase();
        knowledgeBase.setId(id);
        knowledgeBase.setUserId(userId);
        knowledgeBase.setName("Knowledge base");
        knowledgeBase.setDeleted(deleted);
        knowledgeBase.setStatus(status);
        return knowledgeBase;
    }
}
