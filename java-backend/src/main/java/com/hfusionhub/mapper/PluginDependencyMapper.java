package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.PluginDependency;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 插件依赖 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface PluginDependencyMapper extends BaseMapper<PluginDependency> {

    List<PluginDependency> selectByPluginId(@Param("pluginId") Long pluginId);

    int deleteByPluginId(@Param("pluginId") Long pluginId);
}
