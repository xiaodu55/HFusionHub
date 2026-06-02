package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.entity.BidTemplate;
import com.hfusionhub.mapper.BidTemplateMapper;
import com.hfusionhub.service.BidTemplateService;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 标书模板服务单元测试（招投标垂直化 · P2-7 行业方案包 / 模板商城）
 *
 * @author HFusionHub Team
 */
@ExtendWith(MockitoExtension.class)
class BidTemplateServiceImplTest {

    @Mock private BidTemplateMapper templateMapper;

    private BidTemplateService service;

    @BeforeEach
    void setUp() {
        service = new BidTemplateServiceImpl(templateMapper);
    }

    private BidTemplate template(Long id, Long tenantId, String industry) {
        BidTemplate t = new BidTemplate();
        t.setId(id);
        t.setTenantId(tenantId);
        t.setName("工程施工标");
        t.setIndustry(industry);
        t.setSectionDefs("[{\"key\":\"commercial\",\"title\":\"商务标\"}]");
        t.setIsActive(1);
        return t;
    }

    @Test
    void listVisibleIncludesPlatformAndOwn() {
        when(templateMapper.selectList(any()))
                .thenReturn(List.of(template(1L, null, "construction"), template(2L, 7L, "construction")));

        List<BidTemplate> result = service.listVisible(7L, null);

        assertEquals(2, result.size());
        assertNull(result.get(0).getTenantId()); // 平台模板
        assertEquals(7L, result.get(1).getTenantId()); // 自有模板
    }

    @Test
    void listByIndustryFiltersAndExcludesOtherTenants() {
        when(templateMapper.selectList(any())).thenReturn(List.of(template(1L, null, "construction")));

        List<BidTemplate> result = service.listByIndustry("construction", 7L);

        assertEquals(1, result.size());
        verify(templateMapper).selectList(any());
    }

    @Test
    void getByIdVisibleRejectsForeignTenantTemplate() {
        when(templateMapper.selectById(9L)).thenReturn(template(9L, 99L, "it"));
        assertThrows(BusinessException.class, () -> service.getByIdVisible(9L, 7L));
    }

    @Test
    void createSetsTenantAndCreatorAndRejectsBlankName() {
        BidTemplate blank = template(null, 7L, "it");
        blank.setName(" ");
        assertThrows(BusinessException.class, () -> service.create(blank, 7L, 3L));

        BidTemplate valid = template(null, 7L, "it");
        BidTemplate saved = service.create(valid, 7L, 3L);

        assertEquals(7L, saved.getTenantId());
        assertEquals(3L, saved.getCreatedBy());
        assertEquals(1, saved.getIsActive());
        verify(templateMapper).insert(saved);
    }

    @Test
    void updateRejectsPlatformTemplate() {
        BidTemplate platform = template(1L, null, "construction");
        when(templateMapper.selectById(1L)).thenReturn(platform);

        BusinessException ex = assertThrows(
                BusinessException.class, () -> service.update(template(1L, 7L, "construction"), 7L));

        assertEquals(StatusCode.FORBIDDEN, ex.getCode());
    }

    @Test
    void archiveRejectsPlatformTemplateAndArchivesOwn() {
        when(templateMapper.selectById(1L)).thenReturn(template(1L, null, "construction"));
        assertThrows(BusinessException.class, () -> service.archive(1L, 7L));

        BidTemplate own = template(2L, 7L, "construction");
        when(templateMapper.selectById(2L)).thenReturn(own);
        service.archive(2L, 7L);
        assertEquals(0, own.getIsActive());
        verify(templateMapper).updateById(own);
    }

    @Test
    void getByIdVisibleReturnsPlatformTemplate() {
        when(templateMapper.selectById(1L)).thenReturn(template(1L, null, "construction"));
        assertNotNull(service.getByIdVisible(1L, 7L));
    }
}
