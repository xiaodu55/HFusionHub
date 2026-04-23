package com.hfusionhub.service;

import com.hfusionhub.dto.AppApiKeyInfoDTO;
import com.hfusionhub.dto.AppCreateDTO;
import com.hfusionhub.dto.AppInfoDTO;
import java.util.List;

/**
 * 应用（对外发布 Agent）服务
 *
 * @author HFusionHub Team
 */
public interface AppService {

    AppInfoDTO create(AppCreateDTO dto);

    List<AppInfoDTO> listMine();

    AppInfoDTO get(Long id);

    AppInfoDTO update(Long id, AppCreateDTO dto);

    void delete(Long id);

    AppInfoDTO publish(Long id);

    AppInfoDTO unpublish(Long id);

    AppApiKeyInfoDTO createApiKey(Long appId, String name);

    List<AppApiKeyInfoDTO> listApiKeys(Long appId);

    void deleteApiKey(Long appId, Long keyId);
}
