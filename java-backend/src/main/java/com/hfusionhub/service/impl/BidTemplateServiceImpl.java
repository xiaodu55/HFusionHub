package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.entity.BidTemplate;
import com.hfusionhub.mapper.BidTemplateMapper;
import com.hfusionhub.service.BidTemplateService;
import java.util.List;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 标书模板服务实现（招投标垂直化 · P2-7）
 *
 * <p>本表已加入 {@code TENANT_IGNORE_TABLES}（平台模板 tenant_id=NULL 须对租户可见），
 * 租户隔离由服务层完成：平台模板（tenant_id IS NULL）+ 自有模板（tenant_id = ?）。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class BidTemplateServiceImpl implements BidTemplateService {

    private final BidTemplateMapper templateMapper;

    @Override
    public List<BidTemplate> listVisible(Long tenantId, String industry) {
        return templateMapper.selectList(queryVisible(tenantId, industry));
    }

    @Override
    public BidTemplate getByIdVisible(Long id, Long tenantId) {
        BidTemplate template = templateMapper.selectById(id);
        if (template == null || !isVisible(template, tenantId)) {
            throw new BusinessException(StatusCode.NOT_FOUND, "模板不存在");
        }
        return template;
    }

    @Override
    public List<BidTemplate> listByIndustry(String industry, Long tenantId) {
        if (industry == null || industry.isBlank()) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "行业不能为空");
        }
        return templateMapper.selectList(new LambdaQueryWrapper<BidTemplate>()
                .eq(BidTemplate::getIndustry, industry)
                .eq(BidTemplate::getIsActive, 1)
                .and(w -> w.isNull(BidTemplate::getTenantId)
                        .or()
                        .eq(BidTemplate::getTenantId, tenantId)));
    }

    @Override
    @Transactional
    public BidTemplate create(BidTemplate template, Long tenantId, Long userId) {
        if (template.getName() == null || template.getName().isBlank()) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "模板名称不能为空");
        }
        if (template.getSectionDefs() == null || template.getSectionDefs().isBlank()) {
            throw new BusinessException(StatusCode.BAD_REQUEST, "模板分节定义不能为空");
        }
        template.setId(null);
        template.setTenantId(tenantId);
        template.setCreatedBy(userId);
        if (template.getIsActive() == null) {
            template.setIsActive(1);
        }
        templateMapper.insert(template);
        log.info("标书模板已创建: id={}, name={}, tenantId={}", template.getId(), template.getName(), tenantId);
        return template;
    }

    @Override
    @Transactional
    public void update(BidTemplate template, Long tenantId) {
        BidTemplate existing = getByIdVisible(template.getId(), tenantId);
        // 平台级模板禁止租户改写
        if (existing.getTenantId() == null) {
            throw new BusinessException(StatusCode.FORBIDDEN, "平台模板不可修改");
        }
        templateMapper.updateById(template);
        log.info("标书模板已更新: id={}", template.getId());
    }

    @Override
    @Transactional
    public void archive(Long id, Long tenantId) {
        BidTemplate existing = getByIdVisible(id, tenantId);
        if (existing.getTenantId() == null) {
            throw new BusinessException(StatusCode.FORBIDDEN, "平台模板不可归档");
        }
        existing.setIsActive(0);
        templateMapper.updateById(existing);
        log.info("标书模板已归档: id={}", id);
    }

    // ── 私有方法 ────────────────────────────────────────────────

    private LambdaQueryWrapper<BidTemplate> queryVisible(Long tenantId, String industry) {
        LambdaQueryWrapper<BidTemplate> wrapper = new LambdaQueryWrapper<BidTemplate>()
                .eq(BidTemplate::getIsActive, 1)
                .and(w -> w.isNull(BidTemplate::getTenantId)
                        .or()
                        .eq(BidTemplate::getTenantId, tenantId));
        if (industry != null && !industry.isBlank()) {
            wrapper.eq(BidTemplate::getIndustry, industry);
        }
        return wrapper;
    }

    private boolean isVisible(BidTemplate template, Long tenantId) {
        return template.getTenantId() == null
                || tenantId != null && tenantId.equals(template.getTenantId());
    }
}
