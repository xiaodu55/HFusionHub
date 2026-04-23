package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.TenantQuota;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/**
 * 租户配额覆盖 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface TenantQuotaMapper extends BaseMapper<TenantQuota> {

    @Select("SELECT * FROM tenant_quota WHERE tenant_id = #{tenantId} AND meter = #{meter} LIMIT 1")
    TenantQuota selectByTenantAndMeter(@Param("tenantId") Long tenantId, @Param("meter") String meter);
}
