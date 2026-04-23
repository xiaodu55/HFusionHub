package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.AppApiKeyInfoDTO;
import com.hfusionhub.dto.AppCreateDTO;
import com.hfusionhub.dto.AppInfoDTO;
import com.hfusionhub.entity.App;
import com.hfusionhub.entity.AppApiKey;
import com.hfusionhub.entity.KnowledgeBase;
import com.hfusionhub.mapper.AppApiKeyMapper;
import com.hfusionhub.mapper.AppMapper;
import com.hfusionhub.mapper.KnowledgeBaseMapper;
import com.hfusionhub.service.AppService;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.List;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/**
 * 应用服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AppServiceImpl implements AppService {

    private final AppMapper appMapper;
    private final AppApiKeyMapper apiKeyMapper;
    private final KnowledgeBaseMapper knowledgeBaseMapper;

    private static final List<String> ALLOWED_STYLES = List.of("concise", "detailed", "report");
    private static final int STATUS_DRAFT = 0;
    private static final int STATUS_PUBLISHED = 1;
    private static final int STATUS_DISABLED = 2;
    private static final String KEY_PREFIX = "hf_";

    @Override
    @Transactional
    public AppInfoDTO create(AppCreateDTO dto) {
        Long userId = JwtUtils.getCurrentUserId();
        validate(dto, userId);

        App app = new App();
        app.setName(dto.getName().trim());
        app.setDescription(dto.getDescription());
        app.setUserId(userId);
        app.setTenantId(com.hfusionhub.tenant.TenantContext.getTenantId());
        app.setKnowledgeBaseId(dto.getKnowledgeBaseId());
        app.setPromptTemplateId(dto.getPromptTemplateId());
        app.setModel(StringUtils.hasText(dto.getModel()) ? dto.getModel().trim() : null);
        app.setStyle(StringUtils.hasText(dto.getStyle()) ? dto.getStyle() : "detailed");
        app.setStatus(STATUS_DRAFT);
        appMapper.insert(app);
        return toInfoDTO(app);
    }

    @Override
    public List<AppInfoDTO> listMine() {
        Long userId = JwtUtils.getCurrentUserId();
        List<App> apps = appMapper.selectList(
                new LambdaQueryWrapper<App>().eq(App::getUserId, userId).orderByDesc(App::getCreatedAt));
        return apps.stream().map(this::toInfoDTO).collect(Collectors.toList());
    }

    @Override
    public AppInfoDTO get(Long id) {
        return toInfoDTO(requireOwned(id));
    }

    @Override
    @Transactional
    public AppInfoDTO update(Long id, AppCreateDTO dto) {
        App app = requireOwned(id);
        validate(dto, app.getUserId());
        app.setName(dto.getName().trim());
        app.setDescription(dto.getDescription());
        app.setKnowledgeBaseId(dto.getKnowledgeBaseId());
        app.setPromptTemplateId(dto.getPromptTemplateId());
        app.setModel(StringUtils.hasText(dto.getModel()) ? dto.getModel().trim() : null);
        app.setStyle(StringUtils.hasText(dto.getStyle()) ? dto.getStyle() : "detailed");
        appMapper.updateById(app);
        return toInfoDTO(app);
    }

    @Override
    @Transactional
    public void delete(Long id) {
        App app = requireOwned(id);
        appMapper.deleteById(app.getId());
        // 级联软删 API Key
        apiKeyMapper.delete(new LambdaQueryWrapper<AppApiKey>().eq(AppApiKey::getAppId, id));
    }

    @Override
    @Transactional
    public AppInfoDTO publish(Long id) {
        App app = requireOwned(id);
        if (app.getKnowledgeBaseId() == null) {
            throw new BusinessException("请先绑定知识库再发布应用");
        }
        app.setStatus(STATUS_PUBLISHED);
        appMapper.updateById(app);
        return toInfoDTO(app);
    }

    @Override
    @Transactional
    public AppInfoDTO unpublish(Long id) {
        App app = requireOwned(id);
        app.setStatus(STATUS_DRAFT);
        appMapper.updateById(app);
        return toInfoDTO(app);
    }

    @Override
    @Transactional
    public AppApiKeyInfoDTO createApiKey(Long appId, String name) {
        App app = requireOwned(appId);
        if (app.getStatus() != STATUS_PUBLISHED) {
            throw new BusinessException("请先发布应用，再创建 API Key");
        }
        String secret = KEY_PREFIX + randomHex(32);
        AppApiKey key = new AppApiKey();
        key.setAppId(appId);
        key.setName(StringUtils.hasText(name) ? name.trim() : "默认 Key");
        key.setKeyHash(sha256Hex(secret));
        key.setKeyPrefix(secret.substring(0, Math.min(8, secret.length())));
        key.setEnabled(1);
        apiKeyMapper.insert(key);
        log.info("应用 {} 创建 API Key: {}****", appId, key.getKeyPrefix());
        AppApiKeyInfoDTO dto = toKeyDTO(key);
        dto.setSecret(secret); // 明文仅此一次
        return dto;
    }

    @Override
    public List<AppApiKeyInfoDTO> listApiKeys(Long appId) {
        requireOwned(appId);
        return apiKeyMapper
                .selectList(new LambdaQueryWrapper<AppApiKey>()
                        .eq(AppApiKey::getAppId, appId)
                        .orderByDesc(AppApiKey::getCreatedAt))
                .stream()
                .map(this::toKeyDTO)
                .collect(Collectors.toList());
    }

    @Override
    @Transactional
    public void deleteApiKey(Long appId, Long keyId) {
        requireOwned(appId);
        apiKeyMapper.deleteById(keyId);
    }

    // ── helpers ──────────────────────────────────────────────────────────

    private void validate(AppCreateDTO dto, Long userId) {
        if (dto.getKnowledgeBaseId() != null) {
            KnowledgeBase kb = knowledgeBaseMapper.selectById(dto.getKnowledgeBaseId());
            if (kb == null) {
                throw new BusinessException("绑定的知识库不存在");
            }
            if (!kb.getUserId().equals(userId)) {
                throw new BusinessException("无权绑定该知识库");
            }
        }
        if (StringUtils.hasText(dto.getStyle()) && !ALLOWED_STYLES.contains(dto.getStyle())) {
            throw new BusinessException("style 仅允许 concise / detailed / report");
        }
    }

    private App requireOwned(Long id) {
        App app = appMapper.selectById(id);
        if (app == null) {
            throw new BusinessException("应用不存在");
        }
        if (!app.getUserId().equals(JwtUtils.getCurrentUserId())) {
            throw new BusinessException("无权操作该应用");
        }
        return app;
    }

    private AppInfoDTO toInfoDTO(App app) {
        AppInfoDTO dto = new AppInfoDTO();
        dto.setId(app.getId());
        dto.setName(app.getName());
        dto.setDescription(app.getDescription());
        dto.setKnowledgeBaseId(app.getKnowledgeBaseId());
        if (app.getKnowledgeBaseId() != null) {
            KnowledgeBase kb = knowledgeBaseMapper.selectById(app.getKnowledgeBaseId());
            dto.setKnowledgeBaseName(kb == null ? null : kb.getName());
        }
        dto.setPromptTemplateId(app.getPromptTemplateId());
        dto.setModel(app.getModel());
        dto.setStyle(app.getStyle());
        dto.setStatus(app.getStatus());
        dto.setCreatedAt(app.getCreatedAt());
        Long keyCount = apiKeyMapper.selectCount(new LambdaQueryWrapper<AppApiKey>()
                .eq(AppApiKey::getAppId, app.getId())
                .eq(AppApiKey::getEnabled, 1));
        dto.setApiKeyCount(keyCount == null ? 0L : keyCount);
        return dto;
    }

    private AppApiKeyInfoDTO toKeyDTO(AppApiKey key) {
        AppApiKeyInfoDTO dto = new AppApiKeyInfoDTO();
        dto.setId(key.getId());
        dto.setAppId(key.getAppId());
        dto.setName(key.getName());
        dto.setKeyPrefix(key.getKeyPrefix());
        dto.setEnabled(key.getEnabled());
        dto.setCreatedAt(key.getCreatedAt());
        return dto;
    }

    private static String randomHex(int bytes) {
        byte[] buf = new byte[bytes];
        new SecureRandom().nextBytes(buf);
        StringBuilder sb = new StringBuilder(bytes * 2);
        for (byte b : buf) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }

    private static String sha256Hex(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder(hash.length * 2);
            for (byte b : hash) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (Exception e) {
            throw new IllegalStateException("SHA-256 不可用", e);
        }
    }
}
