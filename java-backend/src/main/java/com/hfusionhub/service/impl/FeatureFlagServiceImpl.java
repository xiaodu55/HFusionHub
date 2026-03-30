package com.hfusionhub.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.dto.*;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.entity.FeatureFlag;
import com.hfusionhub.entity.FeatureFlagAuditLog;
import com.hfusionhub.entity.FeatureFlagRule;
import com.hfusionhub.mapper.FeatureFlagAuditLogMapper;
import com.hfusionhub.mapper.FeatureFlagMapper;
import com.hfusionhub.mapper.FeatureFlagRuleMapper;
import com.hfusionhub.service.FeatureFlagService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class FeatureFlagServiceImpl implements FeatureFlagService {

    private final FeatureFlagMapper flagMapper;
    private final FeatureFlagRuleMapper ruleMapper;
    private final FeatureFlagAuditLogMapper auditLogMapper;
    private final ObjectMapper objectMapper;

    private static final int SCOPE_PRIORITY_ENVIRONMENT = 5;
    private static final int SCOPE_PRIORITY_KB          = 4;
    private static final int SCOPE_PRIORITY_USER         = 3;
    private static final int SCOPE_PRIORITY_TENANT       = 2;
    private static final int SCOPE_PRIORITY_GLOBAL       = 1;

    // High-risk flags that require a reason for modification
    private static final java.util.Set<String> HIGH_RISK_FLAGS = java.util.Set.of(
            "agent.write_tools.enabled",
            "agent.web_search.enabled",
            "approval.required_for_write"
    );

    // ──────────── Helper: current user ID ────────────

    private Long currentUserId() {
        try {
            // Sa-Token: try to read from request header
            cn.dev33.satoken.stp.StpUtil.getLoginId(); // throws if not logged in
            Object id = cn.dev33.satoken.stp.StpUtil.getLoginId();
            return id instanceof Long ? (Long) id : Long.valueOf(id.toString());
        } catch (Exception e) {
            return null; // system / migration context
        }
    }

    // ──────────── Flag CRUD ────────────

    @Override
    @Transactional
    public FeatureFlagInfoDTO create(FeatureFlagCreateDTO dto) {
        FeatureFlag flag = new FeatureFlag();
        flag.setFlagKey(dto.getFlagKey());
        flag.setFlagType(dto.getFlagType() != null ? dto.getFlagType() : "boolean");
        flag.setDescription(dto.getDescription());
        flag.setEnabled(dto.getEnabled() != null ? dto.getEnabled() : false);
        flag.setPercentage(dto.getPercentage());
        flag.setWhitelist(dto.getWhitelist());
        flag.setBlacklist(dto.getBlacklist());
        flag.setStartTime(dto.getStartTime());
        flag.setEndTime(dto.getEndTime());
        flagMapper.insert(flag);

        audit(flag.getId(), flag.getFlagKey(), "create", null, toJson(flag),
                dto.getReason(), currentUserId(), "api");
        return toInfoDTO(flag, List.of());
    }

    @Override
    @Transactional
    public FeatureFlagInfoDTO update(Long id, FeatureFlagUpdateDTO dto) {
        FeatureFlag flag = flagMapper.selectById(id);
        if (flag == null) throw new BusinessException(404, "Feature flag not found");

        // Enforce reason for high-risk flags
        if (HIGH_RISK_FLAGS.contains(flag.getFlagKey()) && isBlank(dto.getReason())) {
            throw new BusinessException(400, "Reason is required to modify high-risk flag: " + flag.getFlagKey());
        }

        String oldJson = toJson(flag);

        if (dto.getFlagType()     != null) flag.setFlagType(dto.getFlagType());
        if (dto.getDescription()  != null) flag.setDescription(dto.getDescription());
        if (dto.getEnabled()      != null) flag.setEnabled(dto.getEnabled());
        if (dto.getPercentage()   != null) flag.setPercentage(dto.getPercentage());
        if (dto.getWhitelist()    != null) flag.setWhitelist(dto.getWhitelist());
        if (dto.getBlacklist()    != null) flag.setBlacklist(dto.getBlacklist());
        if (dto.getStartTime()    != null) flag.setStartTime(dto.getStartTime());
        if (dto.getEndTime()      != null) flag.setEndTime(dto.getEndTime());
        flagMapper.updateById(flag);

        audit(flag.getId(), flag.getFlagKey(), "update", oldJson, toJson(flag),
                dto.getReason(), currentUserId(), "api");
        return toInfoDTO(flag, loadRules(id));
    }

    @Override
    @Transactional
    public void delete(Long id) {
        FeatureFlag flag = flagMapper.selectById(id);
        if (flag == null) throw new BusinessException(404, "Feature flag not found");

        if (HIGH_RISK_FLAGS.contains(flag.getFlagKey())) {
            throw new BusinessException(400, "Cannot delete high-risk flag: " + flag.getFlagKey());
        }

        String oldJson = toJson(flag);
        flagMapper.deleteById(id);
        audit(id, flag.getFlagKey(), "delete", oldJson, null, "deleted", currentUserId(), "api");
    }

    @Override
    public FeatureFlagInfoDTO getById(Long id) {
        FeatureFlag flag = flagMapper.selectById(id);
        if (flag == null) throw new BusinessException(404, "Feature flag not found");
        return toInfoDTO(flag, loadRules(id));
    }

    @Override
    public FeatureFlagInfoDTO getByKey(String flagKey) {
        FeatureFlag flag = selectByKey(flagKey);
        if (flag == null) throw new BusinessException(404, "Feature flag not found: " + flagKey);
        return toInfoDTO(flag, loadRules(flag.getId()));
    }

    @Override
    public PageResult<FeatureFlagInfoDTO> list(int page, int pageSize) {
        Page<FeatureFlag> p = flagMapper.selectPage(
                new Page<>(page, pageSize),
                new LambdaQueryWrapper<FeatureFlag>().orderByDesc(FeatureFlag::getCreatedAt));
        List<FeatureFlagInfoDTO> dtos = p.getRecords().stream()
                .map(f -> toInfoDTO(f, loadRules(f.getId())))
                .collect(Collectors.toList());
        return PageResult.of(page, pageSize, p.getTotal(), dtos);
    }

    @Override
    public List<FeatureFlagInfoDTO> listAll() {
        List<FeatureFlag> flags = flagMapper.selectList(
                new LambdaQueryWrapper<FeatureFlag>().orderByAsc(FeatureFlag::getFlagKey));
        Map<Long, List<FeatureFlagRule>> rulesByFlag = ruleMapper.selectList(
                new LambdaQueryWrapper<FeatureFlagRule>().orderByAsc(FeatureFlagRule::getScope))
                .stream().collect(Collectors.groupingBy(FeatureFlagRule::getFlagId));
        return flags.stream()
                .map(f -> toInfoDTO(f, rulesByFlag.getOrDefault(f.getId(), List.of())))
                .collect(Collectors.toList());
    }

    // ──────────── Rules (with audit) ────────────

    @Override
    @Transactional
    public FeatureFlagRuleInfoDTO addRule(Long flagId, FeatureFlagRuleCreateDTO dto) {
        FeatureFlag flag = flagMapper.selectById(flagId);
        if (flag == null) throw new BusinessException(404, "Feature flag not found");

        FeatureFlagRule rule = new FeatureFlagRule();
        rule.setFlagId(flagId);
        rule.setScope(dto.getScope());
        rule.setScopeValue(dto.getScopeValue());
        rule.setEnabled(dto.getEnabled());
        rule.setPercentage(dto.getPercentage());
        rule.setWhitelist(dto.getWhitelist());
        rule.setBlacklist(dto.getBlacklist());
        ruleMapper.insert(rule);

        auditRule(rule.getId(), flag.getFlagKey(), "rule_create", null, toJson(rule),
                currentUserId(), "api");
        return toRuleInfoDTO(rule);
    }

    @Override
    @Transactional
    public FeatureFlagRuleInfoDTO updateRule(Long ruleId, FeatureFlagRuleUpdateDTO dto) {
        FeatureFlagRule rule = ruleMapper.selectById(ruleId);
        if (rule == null) throw new BusinessException(404, "Rule not found");

        String oldJson = toJson(rule);

        if (dto.getScope()       != null) rule.setScope(dto.getScope());
        if (dto.getScopeValue()  != null) rule.setScopeValue(dto.getScopeValue());
        if (dto.getEnabled()     != null) rule.setEnabled(dto.getEnabled());
        if (dto.getPercentage()  != null) rule.setPercentage(dto.getPercentage());
        if (dto.getWhitelist()   != null) rule.setWhitelist(dto.getWhitelist());
        if (dto.getBlacklist()   != null) rule.setBlacklist(dto.getBlacklist());
        ruleMapper.updateById(rule);

        FeatureFlag flag = flagMapper.selectById(rule.getFlagId());
        auditRule(rule.getId(), flag != null ? flag.getFlagKey() : "unknown", "rule_update",
                oldJson, toJson(rule), currentUserId(), "api");
        return toRuleInfoDTO(rule);
    }

    @Override
    @Transactional
    public void deleteRule(Long ruleId) {
        FeatureFlagRule rule = ruleMapper.selectById(ruleId);
        if (rule == null) throw new BusinessException(404, "Rule not found");

        String oldJson = toJson(rule);
        ruleMapper.deleteById(ruleId);

        FeatureFlag flag = flagMapper.selectById(rule.getFlagId());
        auditRule(ruleId, flag != null ? flag.getFlagKey() : "unknown", "rule_delete",
                oldJson, null, currentUserId(), "api");
    }

    // ──────────── Internal snapshot (for Python sync, token-protected) ────────────

    public List<FeatureFlagSnapshotDTO> getSnapshot() {
        List<FeatureFlag> flags = flagMapper.selectList(
                new LambdaQueryWrapper<FeatureFlag>().orderByAsc(FeatureFlag::getFlagKey));
        Map<Long, List<FeatureFlagRule>> rulesByFlag = ruleMapper.selectList(
                new LambdaQueryWrapper<FeatureFlagRule>().orderByAsc(FeatureFlagRule::getScope))
                .stream().collect(Collectors.groupingBy(FeatureFlagRule::getFlagId));
        return flags.stream()
                .map(f -> toSnapshotDTO(f, rulesByFlag.getOrDefault(f.getId(), List.of())))
                .collect(Collectors.toList());
    }

    // ──────────── Evaluation (core) ────────────

    @Override
    public FeatureFlagEvaluateResultDTO evaluate(FeatureFlagEvaluateDTO dto) {
        FeatureFlag flag = selectByKey(dto.getFlagKey());
        if (flag == null)
            return new FeatureFlagEvaluateResultDTO(dto.getFlagKey(), false, "not_found", null,
                    "Flag does not exist");

        // 1. Time window check
        LocalDateTime now = LocalDateTime.now();
        if (flag.getStartTime() != null && now.isBefore(flag.getStartTime()))
            return new FeatureFlagEvaluateResultDTO(dto.getFlagKey(), false, "time_window", null,
                    "Flag not yet active");
        if (flag.getEndTime() != null && now.isAfter(flag.getEndTime()))
            return new FeatureFlagEvaluateResultDTO(dto.getFlagKey(), false, "time_window", null,
                    "Flag expired");

        // 2. Load rules, sort by priority descending
        List<FeatureFlagRule> rules = loadRules(flag.getId()).stream()
                .sorted(Comparator.comparingInt((FeatureFlagRule r) -> scopePriority(r.getScope())).reversed())
                .collect(Collectors.toList());

        // 3. Try each rule in priority order
        for (FeatureFlagRule rule : rules) {
            if (!scopeMatches(rule, dto)) continue;

            Boolean effective = resolveEnabled(flag, rule, dto.getUserId());
            String reason = String.format("Rule [%s:%s] matched → enabled=%s",
                    rule.getScope(), rule.getScopeValue(), effective);
            return new FeatureFlagEvaluateResultDTO(dto.getFlagKey(), effective, rule.getScope(), rule.getId(), reason);
        }

        // 4. No rule matched → global default
        return new FeatureFlagEvaluateResultDTO(dto.getFlagKey(), flag.getEnabled(), "global", null,
                "No matching rule; using global default");
    }

    @Override
    public boolean isEnabled(String flagKey, Long userId, Long knowledgeBaseId, Long tenantId, String environment) {
        FeatureFlagEvaluateDTO dto = new FeatureFlagEvaluateDTO();
        dto.setFlagKey(flagKey);
        dto.setUserId(userId);
        dto.setKnowledgeBaseId(knowledgeBaseId);
        dto.setTenantId(tenantId);
        dto.setEnvironment(environment);
        return evaluate(dto).isEnabled();
    }

    // ──────────── Helpers ────────────

    private FeatureFlag selectByKey(String flagKey) {
        return flagMapper.selectOne(
                new LambdaQueryWrapper<FeatureFlag>()
                        .eq(FeatureFlag::getFlagKey, flagKey)
                        .last("LIMIT 1"));
    }

    private List<FeatureFlagRule> loadRules(Long flagId) {
        return ruleMapper.selectList(
                new LambdaQueryWrapper<FeatureFlagRule>()
                        .eq(FeatureFlagRule::getFlagId, flagId)
                        .orderByAsc(FeatureFlagRule::getScope));
    }

    private boolean scopeMatches(FeatureFlagRule rule, FeatureFlagEvaluateDTO ctx) {
        return switch (rule.getScope()) {
            case "global"      -> true;
            case "tenant"      -> ctx.getTenantId()    != null && String.valueOf(ctx.getTenantId()).equals(rule.getScopeValue());
            case "user"        -> ctx.getUserId()      != null && String.valueOf(ctx.getUserId()).equals(rule.getScopeValue());
            case "kb"          -> ctx.getKnowledgeBaseId() != null && String.valueOf(ctx.getKnowledgeBaseId()).equals(rule.getScopeValue());
            case "environment" -> ctx.getEnvironment() != null && ctx.getEnvironment().equalsIgnoreCase(rule.getScopeValue());
            default -> false;
        };
    }

    /**
     * Resolve enabled with FIXED order: blacklist → whitelist → percentage → default.
     * <p>
     * The rule's {@code enabled} field provides the base value.  Lists and
     * percentages are overlays that can flip the result:
     * <ul>
     *   <li>blacklist match  → always {@code false}</li>
     *   <li>whitelist match  → {@code base}</li>
     *   <li>percentage match → {@code base AND in-percentage}</li>
     *   <li>otherwise        → {@code base}</li>
     * </ul>
     */
    private Boolean resolveEnabled(FeatureFlag flag, FeatureFlagRule rule, Long userId) {
        Boolean base = rule.getEnabled() != null ? rule.getEnabled() : flag.getEnabled();

        // Resolve effective overrides (rule wins over flag)
        String bl  = rule.getBlacklist()  != null ? rule.getBlacklist()  : flag.getBlacklist();
        String wl  = rule.getWhitelist()  != null ? rule.getWhitelist()  : flag.getWhitelist();
        Integer pct = rule.getPercentage() != null ? rule.getPercentage() : flag.getPercentage();

        // 1. Blacklist (highest priority — always deny)
        if (bl != null && userId != null && jsonArrayContains(bl, String.valueOf(userId)))
            return false;

        // 2. Whitelist (if present, user must be in it)
        if (wl != null && userId != null) {
            return base && jsonArrayContains(wl, String.valueOf(userId));
        }

        // 3. Percentage rollout
        if (pct != null && userId != null) {
            long hash = deterministicHash(flag.getFlagKey() + ":" + userId);
            boolean inPercentage = (Math.abs(hash) % 100) < pct;
            return base && inPercentage;
        }

        // 4. Default
        return base;
    }

    private static boolean jsonArrayContains(String jsonArray, String value) {
        try {
            String[] items = jsonArray.replaceAll("[\\[\\]\\s]", "").split(",");
            return Arrays.stream(items).map(String::trim).anyMatch(v -> v.equals(value));
        } catch (Exception e) {
            return false;
        }
    }

    private static int scopePriority(String scope) {
        return switch (scope) {
            case "environment" -> SCOPE_PRIORITY_ENVIRONMENT;
            case "kb"          -> SCOPE_PRIORITY_KB;
            case "user"        -> SCOPE_PRIORITY_USER;
            case "tenant"      -> SCOPE_PRIORITY_TENANT;
            case "global"      -> SCOPE_PRIORITY_GLOBAL;
            default            -> 0;
        };
    }

    private static long deterministicHash(String input) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] digest = md.digest(input.getBytes(StandardCharsets.UTF_8));
            long hash = 0;
            for (int i = 0; i < 8; i++) {
                hash = (hash << 8) | (digest[i] & 0xFF);
            }
            return hash;
        } catch (Exception e) {
            return input.hashCode();
        }
    }

    // ──────────── Audit ────────────

    private void audit(Long flagId, String flagKey, String action,
                       String oldVal, String newVal, String reason,
                       Long operatorId, String source) {
        FeatureFlagAuditLog logEntry = new FeatureFlagAuditLog();
        logEntry.setFlagId(flagId);
        logEntry.setFlagKey(flagKey);
        logEntry.setAction(action);
        logEntry.setOldValue(oldVal);
        logEntry.setNewValue(newVal);
        logEntry.setReason(reason);
        logEntry.setOperatorId(operatorId);
        logEntry.setCreatedAt(LocalDateTime.now());
        auditLogMapper.insert(logEntry);
        log.info("Feature flag audit: action={}, flagKey={}, operatorId={}, source={}",
                action, flagKey, operatorId, source);
    }

    private void auditRule(Long ruleId, String flagKey, String action,
                           String oldVal, String newVal, Long operatorId, String source) {
        // Store rule audit in the same table, using the flagKey for traceability
        FeatureFlagAuditLog logEntry = new FeatureFlagAuditLog();
        logEntry.setFlagId(ruleId); // rule ID stored in flagId column for rule-level audits
        logEntry.setFlagKey(flagKey + "#rule");
        logEntry.setAction(action);
        logEntry.setOldValue(oldVal);
        logEntry.setNewValue(newVal);
        logEntry.setOperatorId(operatorId);
        logEntry.setCreatedAt(LocalDateTime.now());
        auditLogMapper.insert(logEntry);
        log.info("Feature flag rule audit: action={}, flagKey={}, ruleId={}, operatorId={}, source={}",
                action, flagKey, ruleId, operatorId, source);
    }

    private String toJson(Object obj) {
        try { return objectMapper.writeValueAsString(obj); }
        catch (Exception e) { return "{}"; }
    }

    private static boolean isBlank(String s) {
        return s == null || s.trim().isEmpty();
    }

    private FeatureFlagInfoDTO toInfoDTO(FeatureFlag f, List<FeatureFlagRule> rules) {
        FeatureFlagInfoDTO dto = new FeatureFlagInfoDTO();
        dto.setId(f.getId());
        dto.setFlagKey(f.getFlagKey());
        dto.setFlagType(f.getFlagType());
        dto.setDescription(f.getDescription());
        dto.setEnabled(f.getEnabled());
        dto.setPercentage(f.getPercentage());
        dto.setWhitelist(f.getWhitelist());
        dto.setBlacklist(f.getBlacklist());
        dto.setStartTime(f.getStartTime());
        dto.setEndTime(f.getEndTime());
        dto.setCreatedAt(f.getCreatedAt());
        dto.setUpdatedAt(f.getUpdatedAt());
        dto.setRules(rules.stream().map(this::toRuleInfoDTO).collect(Collectors.toList()));
        return dto;
    }

    private FeatureFlagRuleInfoDTO toRuleInfoDTO(FeatureFlagRule r) {
        FeatureFlagRuleInfoDTO dto = new FeatureFlagRuleInfoDTO();
        dto.setId(r.getId());
        dto.setFlagId(r.getFlagId());
        dto.setScope(r.getScope());
        dto.setScopeValue(r.getScopeValue());
        dto.setEnabled(r.getEnabled());
        dto.setPercentage(r.getPercentage());
        dto.setWhitelist(r.getWhitelist());
        dto.setBlacklist(r.getBlacklist());
        return dto;
    }

    private FeatureFlagSnapshotDTO toSnapshotDTO(FeatureFlag f, List<FeatureFlagRule> rules) {
        FeatureFlagSnapshotDTO dto = new FeatureFlagSnapshotDTO();
        dto.setFlagKey(f.getFlagKey());
        dto.setEnabled(f.getEnabled());
        dto.setFlagType(f.getFlagType());
        dto.setPercentage(f.getPercentage());
        dto.setWhitelist(f.getWhitelist());
        dto.setBlacklist(f.getBlacklist());
        dto.setStartTime(f.getStartTime());
        dto.setEndTime(f.getEndTime());
        dto.setRules(rules.stream().map(this::toSnapshotRuleDTO).collect(Collectors.toList()));
        return dto;
    }

    private FeatureFlagSnapshotDTO.SnapshotRule toSnapshotRuleDTO(FeatureFlagRule r) {
        FeatureFlagSnapshotDTO.SnapshotRule sr = new FeatureFlagSnapshotDTO.SnapshotRule();
        sr.setScope(r.getScope());
        sr.setScopeValue(r.getScopeValue());
        sr.setEnabled(r.getEnabled());
        sr.setPercentage(r.getPercentage());
        sr.setWhitelist(r.getWhitelist());
        sr.setBlacklist(r.getBlacklist());
        return sr;
    }
}
