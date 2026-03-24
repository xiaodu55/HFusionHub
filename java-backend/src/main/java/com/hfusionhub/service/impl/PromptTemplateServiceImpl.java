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
import com.hfusionhub.service.PromptTemplateService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.List;

@Service
@RequiredArgsConstructor
public class PromptTemplateServiceImpl implements PromptTemplateService {

    private final PromptTemplateMapper promptTemplateMapper;
    private final PromptTemplateVersionMapper versionMapper;

    // ── CRUD ──────────────────────────────────────────────────────────

    @Override
    public List<PromptTemplateInfoDTO> listMine() {
        Long userId = JwtUtils.getCurrentUserId();
        return promptTemplateMapper.selectList(new LambdaQueryWrapper<PromptTemplate>()
                        .eq(PromptTemplate::getUserId, userId)
                        .orderByDesc(PromptTemplate::getUpdatedAt))
                .stream().map(this::toInfo).toList();
    }

    @Override
    @Transactional
    public PromptTemplateInfoDTO create(PromptTemplateSaveDTO dto) {
        Long userId = JwtUtils.getCurrentUserId();
        ensureNameAvailable(dto.getName(), userId, null);
        PromptTemplate template = new PromptTemplate();
        template.setUserId(userId);
        apply(template, dto);
        template.setStatus(PromptTemplate.STATUS_DRAFT);
        template.setVersion(1);
        promptTemplateMapper.insert(template);

        // Snapshot the new v1 state AFTER insert (operation = CREATE)
        insertVersion(template, PromptTemplateVersion.OP_CREATE, userId);
        return toInfo(template);
    }

    @Override
    @Transactional
    public PromptTemplateInfoDTO update(Long id, PromptTemplateSaveDTO dto) {
        PromptTemplate template = requireOwned(id, JwtUtils.getCurrentUserId());
        ensureNameAvailable(dto.getName(), template.getUserId(), id);
        boolean changed = !template.getName().equals(dto.getName().trim())
                || !same(template.getDescription(), clean(dto.getDescription()))
                || !template.getContent().equals(dto.getContent().trim());

        if (changed) {
            apply(template, dto);
            template.setVersion((template.getVersion() == null ? 1 : template.getVersion()) + 1);
            template.setStatus(PromptTemplate.STATUS_DRAFT);
            promptTemplateMapper.updateById(template);

            // Snapshot the NEW state AFTER increment (operation = EDIT)
            insertVersion(template, PromptTemplateVersion.OP_EDIT, JwtUtils.getCurrentUserId());
        } else {
            apply(template, dto);
            promptTemplateMapper.updateById(template);
        }
        return toInfo(template);
    }

    @Override
    @Transactional
    public PromptTemplateInfoDTO publish(Long id) {
        PromptTemplate template = requireOwned(id, JwtUtils.getCurrentUserId());
        template.setStatus(PromptTemplate.STATUS_PUBLISHED);
        promptTemplateMapper.updateById(template);

        // Snapshot AFTER status change (operation = PUBLISH, same version)
        insertVersion(template, PromptTemplateVersion.OP_PUBLISH, JwtUtils.getCurrentUserId());
        return toInfo(template);
    }

    @Override
    @Transactional
    public PromptTemplateInfoDTO unpublish(Long id) {
        PromptTemplate template = requireOwned(id, JwtUtils.getCurrentUserId());
        template.setStatus(PromptTemplate.STATUS_DRAFT);
        promptTemplateMapper.updateById(template);

        // Snapshot AFTER status change (operation = UNPUBLISH, same version)
        insertVersion(template, PromptTemplateVersion.OP_UNPUBLISH, JwtUtils.getCurrentUserId());
        return toInfo(template);
    }

    @Override
    @Transactional
    public void delete(Long id) {
        promptTemplateMapper.deleteById(requireOwned(id, JwtUtils.getCurrentUserId()).getId());
    }

    @Override
    public PromptTemplate getPublishedOwned(Long id, Long userId) {
        if (id == null || userId == null) return null;
        return promptTemplateMapper.selectOne(new LambdaQueryWrapper<PromptTemplate>()
                .eq(PromptTemplate::getId, id)
                .eq(PromptTemplate::getUserId, userId)
                .eq(PromptTemplate::getStatus, PromptTemplate.STATUS_PUBLISHED));
    }

    // ── Version history ───────────────────────────────────────────────

    @Override
    public List<PromptTemplateVersionDTO> listVersions(Long templateId) {
        requireOwned(templateId, JwtUtils.getCurrentUserId());
        return versionMapper.selectList(
                new LambdaQueryWrapper<PromptTemplateVersion>()
                        .eq(PromptTemplateVersion::getTemplateId, templateId)
                        .orderByDesc(PromptTemplateVersion::getVersion)
                        .orderByDesc(PromptTemplateVersion::getId))
                .stream().map(this::toVersionDTO).toList();
    }

    @Override
    @Transactional
    public PromptTemplateInfoDTO rollback(Long templateId, Long versionId) {
        Long userId = JwtUtils.getCurrentUserId();
        PromptTemplate template = requireOwned(templateId, userId);

        // Find the target snapshot by its primary key (unambiguous)
        PromptTemplateVersion target = versionMapper.selectById(versionId);
        if (target == null || !target.getTemplateId().equals(templateId)) {
            throw new BusinessException("版本快照不存在或不属于该模板");
        }

        // Check name uniqueness — the old name might now be taken by another template
        if (!target.getName().equals(template.getName())) {
            ensureNameAvailable(target.getName(), userId, templateId);
        }

        // Restore from target snapshot
        template.setName(target.getName());
        template.setDescription(target.getDescription());
        template.setContent(target.getContent());
        template.setVersion((template.getVersion() == null ? 1 : template.getVersion()) + 1);
        template.setStatus(PromptTemplate.STATUS_DRAFT);
        promptTemplateMapper.updateById(template);

        // Snapshot the NEW rolled-back state AFTER increment (operation = ROLLBACK)
        insertVersion(template, PromptTemplateVersion.OP_ROLLBACK, userId);

        return toInfo(template);
    }

    // ── Private helpers ───────────────────────────────────────────────

    private PromptTemplate requireOwned(Long id, Long userId) {
        PromptTemplate template = promptTemplateMapper.selectById(id);
        if (template == null) throw new BusinessException("提示词模板不存在或已删除");
        if (!template.getUserId().equals(userId)) throw new BusinessException("无权操作该提示词模板");
        return template;
    }

    private void ensureNameAvailable(String rawName, Long userId, Long ignoredId) {
        String name = rawName == null ? "" : rawName.trim();
        LambdaQueryWrapper<PromptTemplate> query = new LambdaQueryWrapper<PromptTemplate>()
                .eq(PromptTemplate::getUserId, userId)
                .eq(PromptTemplate::getName, name);
        if (ignoredId != null) query.ne(PromptTemplate::getId, ignoredId);
        if (promptTemplateMapper.selectCount(query) > 0) {
            throw new BusinessException("已经存在同名提示词模板");
        }
    }

    private void apply(PromptTemplate template, PromptTemplateSaveDTO dto) {
        template.setName(dto.getName().trim());
        template.setDescription(clean(dto.getDescription()));
        template.setContent(dto.getContent().trim());
    }

    private String clean(String value) {
        return StringUtils.hasText(value) ? value.trim() : null;
    }

    private boolean same(String left, String right) {
        return left == null ? right == null : left.equals(right);
    }

    private void insertVersion(PromptTemplate template, String operation, Long operatorId) {
        PromptTemplateVersion v = new PromptTemplateVersion();
        v.setTemplateId(template.getId());
        v.setVersion(template.getVersion());
        v.setName(template.getName());
        v.setDescription(template.getDescription());
        v.setContent(template.getContent());
        v.setStatus(template.getStatus());
        v.setOperation(operation);
        v.setOperatorId(operatorId);
        versionMapper.insert(v);
    }

    private PromptTemplateInfoDTO toInfo(PromptTemplate template) {
        return PromptTemplateInfoDTO.builder()
                .id(template.getId())
                .name(template.getName())
                .description(template.getDescription())
                .content(template.getContent())
                .status(template.getStatus())
                .version(template.getVersion())
                .createdAt(template.getCreatedAt())
                .updatedAt(template.getUpdatedAt())
                .build();
    }

    private PromptTemplateVersionDTO toVersionDTO(PromptTemplateVersion v) {
        return PromptTemplateVersionDTO.builder()
                .id(v.getId())
                .version(v.getVersion())
                .name(v.getName())
                .description(v.getDescription())
                .content(v.getContent())
                .status(v.getStatus())
                .operation(v.getOperation())
                .operatorId(v.getOperatorId())
                .createdAt(v.getCreatedAt())
                .build();
    }
}
