package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.PluginAuditLog;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 插件审计日志 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface PluginAuditLogMapper extends BaseMapper<PluginAuditLog> {

    List<PluginAuditLog> selectByPluginId(@Param("pluginId") Long pluginId, @Param("limit") int limit);

    List<PluginAuditLog> selectByOperatorId(@Param("operatorId") Long operatorId, @Param("limit") int limit);

    PluginAuditLog selectByEventId(@Param("eventId") String eventId);
}
