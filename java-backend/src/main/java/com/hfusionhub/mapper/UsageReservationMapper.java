package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.UsageReservation;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/**
 * 用量预占状态机 Mapper
 *
 * <p>终态转换（COMMIT / RELEASE）通过带 {@code state = 'RESERVED'} 条件的 UPDATE 原子完成：
 * affected rows = 1 表示本请求成功独占转换；0 表示并发线程已先行转换（重读后按新状态处理）。</p>
 *
 * @author HFusionHub Team
 */
@Mapper
public interface UsageReservationMapper extends BaseMapper<UsageReservation> {

    @Select("SELECT * FROM usage_reservation WHERE tenant_id = #{tenantId} AND meter = #{meter} "
            + "AND request_id = #{requestId} LIMIT 1")
    UsageReservation selectByKey(
            @Param("tenantId") Long tenantId, @Param("meter") String meter, @Param("requestId") String requestId);

    /**
     * RESERVED → COMMITTED（独占，仅当仍处于 RESERVED 时成功）。
     */
    @Update("UPDATE usage_reservation SET state = 'COMMITTED', actual_amount = #{actualAmount} "
            + "WHERE tenant_id = #{tenantId} AND meter = #{meter} AND request_id = #{requestId} "
            + "AND state = 'RESERVED'")
    int tryCommit(
            @Param("tenantId") Long tenantId,
            @Param("meter") String meter,
            @Param("requestId") String requestId,
            @Param("actualAmount") long actualAmount);

    /**
     * RESERVED → RELEASED（独占，仅当仍处于 RESERVED 时成功）。
     */
    @Update("UPDATE usage_reservation SET state = 'RELEASED' "
            + "WHERE tenant_id = #{tenantId} AND meter = #{meter} AND request_id = #{requestId} "
            + "AND state = 'RESERVED'")
    int tryRelease(
            @Param("tenantId") Long tenantId, @Param("meter") String meter, @Param("requestId") String requestId);

    /** Stale plugin reservations are recoverable because plugin runtime has no durable worker lease. */
    @Select("SELECT * FROM usage_reservation WHERE meter = 'plugin_executions' AND state = 'RESERVED' "
            + "AND updated_at < #{staleBefore} ORDER BY id ASC LIMIT #{limit}")
    List<UsageReservation> selectStalePluginReservations(
            @Param("staleBefore") LocalDateTime staleBefore, @Param("limit") int limit);
}
