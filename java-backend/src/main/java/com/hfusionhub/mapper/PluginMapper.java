package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.Plugin;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/**
 * 插件 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface PluginMapper extends BaseMapper<Plugin> {

    Plugin selectByPluginId(@Param("pluginId") String pluginId);

    Plugin selectByNameVersion(@Param("name") String name, @Param("version") String version);

    Plugin selectByNameVersionAny(@Param("name") String name, @Param("version") String version);

    List<Plugin> selectEnabledPlugins();

    List<Plugin> selectCircuitOpenPlugins();

    int updateStatus(@Param("id") Long id, @Param("status") String status);

    int updateEnabled(@Param("id") Long id, @Param("enabled") Boolean enabled);

    int updateArtifact(@Param("id") Long id,
                       @Param("artifactPath") String artifactPath,
                       @Param("artifactHash") String artifactHash);

    int updateCanary(@Param("id") Long id, @Param("canaryWeight") java.math.BigDecimal canaryWeight);

    int updateHealth(@Param("id") Long id, @Param("healthStatus") String healthStatus);

    int updateVulnerability(@Param("id") Long id, @Param("vulnerabilityStatus") String vulnerabilityStatus);

    int updateContainerImage(@Param("id") Long id, @Param("containerImage") String containerImage);

    int openCircuitBreaker(@Param("id") Long id, @Param("cooldownMinutes") int cooldownMinutes);

    int countActiveByUserId(@Param("userId") Long userId);

    /**
     * Get all versions of a plugin (by name) for canary routing.
     * Returns all enabled plugins with the same name, ordered by version.
     */
    List<Plugin> selectVersionsByPluginName(@Param("name") String name);
}
