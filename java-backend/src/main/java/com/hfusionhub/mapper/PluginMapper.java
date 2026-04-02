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

    int updateStatus(@Param("id") Long id, @Param("status") String status);

    int updateEnabled(@Param("id") Long id, @Param("enabled") Boolean enabled);

    int updateArtifact(@Param("id") Long id,
                       @Param("artifactPath") String artifactPath,
                       @Param("artifactHash") String artifactHash);

    int countActiveByUserId(@Param("userId") Long userId);
}
