package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.MemoryEntry;
import com.hfusionhub.mapper.MemoryEntryMapper;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class MemoryServiceImplTest {

    @Mock
    private MemoryEntryMapper memoryEntryMapper;

    @InjectMocks
    private MemoryServiceImpl memoryService;

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

    @Test
    void saveShouldSetUserIdAndDefaultImportance() {
        MemoryEntry entry = new MemoryEntry();
        entry.setType("entity_fact");
        entry.setContent("用户喜欢 Python");

        when(memoryEntryMapper.insert(any(MemoryEntry.class))).thenReturn(1);

        MemoryEntry result = memoryService.save(entry);

        assertEquals(1L, result.getUserId());
        assertEquals(0.5, result.getImportance());
        verify(memoryEntryMapper).insert(entry);
    }

    @Test
    void saveShouldKeepExplicitImportance() {
        MemoryEntry entry = new MemoryEntry();
        entry.setType("user_preference");
        entry.setContent("偏好");
        entry.setImportance(0.9);

        when(memoryEntryMapper.insert(any(MemoryEntry.class))).thenReturn(1);

        MemoryEntry result = memoryService.save(entry);

        assertEquals(0.9, result.getImportance());
    }

    @Test
    void listByUserShouldFilterByTypeAndConversation() {
        when(memoryEntryMapper.selectList(any(LambdaQueryWrapper.class))).thenReturn(List.of());

        List<MemoryEntry> result = memoryService.listByUser("entity_fact", 5L);

        assertNotNull(result);
        assertTrue(result.isEmpty());
        verify(memoryEntryMapper).selectList(any(LambdaQueryWrapper.class));
    }

    @Test
    void listByUserShouldAcceptNullFilters() {
        when(memoryEntryMapper.selectList(any(LambdaQueryWrapper.class))).thenReturn(List.of());

        List<MemoryEntry> result = memoryService.listByUser(null, null);

        assertNotNull(result);
        verify(memoryEntryMapper).selectList(any(LambdaQueryWrapper.class));
    }

    @Test
    void deleteShouldThrowWhenEntryNotFound() {
        when(memoryEntryMapper.selectById(100L)).thenReturn(null);

        assertThrows(BusinessException.class, () -> memoryService.delete(100L));
    }

    @Test
    void deleteShouldThrowWhenNotOwner() {
        MemoryEntry entry = new MemoryEntry();
        entry.setId(1L);
        entry.setUserId(999L); // different user

        when(memoryEntryMapper.selectById(1L)).thenReturn(entry);

        assertThrows(BusinessException.class, () -> memoryService.delete(1L));
    }

    @Test
    void deleteShouldSucceedForOwner() {
        MemoryEntry entry = new MemoryEntry();
        entry.setId(1L);
        entry.setUserId(1L); // same user as JwtUtils returns

        when(memoryEntryMapper.selectById(1L)).thenReturn(entry);
        when(memoryEntryMapper.deleteById(1L)).thenReturn(1);

        assertDoesNotThrow(() -> memoryService.delete(1L));
    }

    @Test
    void getRelevantMemoriesShouldReturnEntityFactsAndPreferences() {
        when(memoryEntryMapper.selectList(any(LambdaQueryWrapper.class))).thenReturn(List.of());

        List<MemoryEntry> result = memoryService.getRelevantMemories(1L, "Python", 5);

        assertNotNull(result);
        verify(memoryEntryMapper).selectList(any(LambdaQueryWrapper.class));
    }
}
