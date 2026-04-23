package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.UsageCounter;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/**
 * 每日用量计数器 Mapper — 原子条件增减。
 *
 * <p>预占通过带限额条件的 UPDATE 完成：只有 {@code committed + reserved + amount <= limit}
 * 时才更新成功（affected rows = 1），否则不命中（affected rows = 0），由服务层判定超限。</p>
 *
 * @author HFusionHub Team
 */
@Mapper
public interface UsageCounterMapper extends BaseMapper<UsageCounter> {

    @Select("SELECT * FROM usage_counter WHERE tenant_id = #{tenantId} AND meter = #{meter} "
            + "AND window_key = #{windowKey} LIMIT 1")
    UsageCounter selectByKey(
            @Param("tenantId") Long tenantId, @Param("meter") String meter, @Param("windowKey") String windowKey);

    /**
     * 原子预占：命中并累加 reserved，否则返回 0（超限或行不存在）。
     * 行不存在时调用方先通过 {@link #ensureRow} 保证存在。
     */
    @Update("UPDATE usage_counter SET reserved = reserved + #{amount} "
            + "WHERE tenant_id = #{tenantId} AND meter = #{meter} AND window_key = #{windowKey} "
            + "AND committed + reserved + #{amount} <= #{limitValue}")
    int tryReserve(
            @Param("tenantId") Long tenantId,
            @Param("meter") String meter,
            @Param("windowKey") String windowKey,
            @Param("amount") long amount,
            @Param("limitValue") long limitValue);

    /**
     * 结算：committed 累加实际消耗，reserved 退回预占量。
     * 带 {@code reserved >= reservedAmount} 守卫，reserved 永不为负。
     */
    @Update("UPDATE usage_counter SET committed = committed + #{actualAmount}, "
            + "reserved = reserved - #{reservedAmount} "
            + "WHERE tenant_id = #{tenantId} AND meter = #{meter} AND window_key = #{windowKey} "
            + "AND reserved >= #{reservedAmount}")
    int settle(
            @Param("tenantId") Long tenantId,
            @Param("meter") String meter,
            @Param("windowKey") String windowKey,
            @Param("actualAmount") long actualAmount,
            @Param("reservedAmount") long reservedAmount);

    /**
     * 退回预占（失败/取消时释放容量）。带 {@code reserved >= reservedAmount} 守卫。
     */
    @Update("UPDATE usage_counter SET reserved = reserved - #{reservedAmount} "
            + "WHERE tenant_id = #{tenantId} AND meter = #{meter} AND window_key = #{windowKey} "
            + "AND reserved >= #{reservedAmount}")
    int release(
            @Param("tenantId") Long tenantId,
            @Param("meter") String meter,
            @Param("windowKey") String windowKey,
            @Param("reservedAmount") long reservedAmount);
}
