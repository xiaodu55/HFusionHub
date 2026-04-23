package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.UsageEvent;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/**
 * 用量账本事件 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface UsageEventMapper extends BaseMapper<UsageEvent> {

    /**
     * 按 (租户, 计量项, 业务幂等键, 操作) 查询唯一事件（幂等判重用）。
     */
    @Select("SELECT * FROM usage_event WHERE tenant_id = #{tenantId} AND meter = #{meter} "
            + "AND request_id = #{requestId} AND operation = #{operation} LIMIT 1")
    UsageEvent selectByRequestAndOperation(
            @Param("tenantId") Long tenantId,
            @Param("meter") String meter,
            @Param("requestId") String requestId,
            @Param("operation") String operation);
}
