package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.PromptTemplateInfoDTO;
import com.hfusionhub.dto.PromptTemplateSaveDTO;
import com.hfusionhub.entity.PromptTemplate;
import com.hfusionhub.mapper.PromptTemplateMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class PromptTemplateServiceImplTest {

    @Mock
    private PromptTemplateMapper promptTemplateMapper;

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
    }

    @Test
    void publishRejectsTemplatesOwnedByAnotherUser() {
        PromptTemplate template = new PromptTemplate();
        template.setId(3L);
        template.setUserId(8L);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);

        assertThrows(BusinessException.class, () -> promptTemplateService.publish(3L));
    }

    @Test
    void updateIncrementsVersionOnlyWhenContentChanges() {
        PromptTemplate template = new PromptTemplate();
        template.setId(3L);
        template.setUserId(7L);
        template.setName("客服助手");
        template.setDescription(null);
        template.setContent("简洁回答");
        template.setVersion(2);
        template.setStatus(PromptTemplate.STATUS_DRAFT);
        when(promptTemplateMapper.selectById(3L)).thenReturn(template);
        when(promptTemplateMapper.selectCount(any(LambdaQueryWrapper.class))).thenReturn(0L);

        PromptTemplateInfoDTO result = promptTemplateService.update(3L, save("客服助手", "先给结论"));

        assertEquals(3, result.getVersion());
        verify(promptTemplateMapper).updateById(template);
    }

    private PromptTemplateSaveDTO save(String name, String content) {
        PromptTemplateSaveDTO dto = new PromptTemplateSaveDTO();
        dto.setName(name);
        dto.setContent(content);
        return dto;
    }
}
