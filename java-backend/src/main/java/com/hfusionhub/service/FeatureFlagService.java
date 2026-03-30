package com.hfusionhub.service;

import com.hfusionhub.common.dto.*;

import java.util.List;

public interface FeatureFlagService {

    FeatureFlagInfoDTO create(FeatureFlagCreateDTO dto);

    FeatureFlagInfoDTO update(Long id, FeatureFlagUpdateDTO dto);

    void delete(Long id);

    FeatureFlagInfoDTO getById(Long id);

    FeatureFlagInfoDTO getByKey(String flagKey);

    PageResult<FeatureFlagInfoDTO> list(int page, int pageSize);

    List<FeatureFlagInfoDTO> listAll();

    FeatureFlagRuleInfoDTO addRule(Long flagId, FeatureFlagRuleCreateDTO dto);

    FeatureFlagRuleInfoDTO updateRule(Long ruleId, FeatureFlagRuleUpdateDTO dto);

    void deleteRule(Long ruleId);

    FeatureFlagEvaluateResultDTO evaluate(FeatureFlagEvaluateDTO dto);

    boolean isEnabled(String flagKey, Long userId, Long knowledgeBaseId, Long tenantId, String environment);

    List<FeatureFlagSnapshotDTO> getSnapshot();
}
