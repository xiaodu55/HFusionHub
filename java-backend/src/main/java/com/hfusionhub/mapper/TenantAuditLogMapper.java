package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.TenantAuditLog;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 跨租户代操作审计 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface TenantAuditLogMapper extends BaseMapper<TenantAuditLog> {

    int insertCrossTenant(
            @Param("operatorId") Long operatorId,
            @Param("fromTenant") Long fromTenant,
            @Param("toTenant") Long toTenant,
            @Param("action") String action);
}
