package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.dto.DailyCostDTO;
import com.hfusionhub.entity.ModelUsageRecord;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 模型调用成本记录 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface ModelUsageRecordMapper extends BaseMapper<ModelUsageRecord> {

    /**
     * 按天统计某用户最近一段时间的成本（由租户行拦截器附加租户隔离条件）。
     *
     * <p>起始时间由服务层按天数计算后传入（避免 DATE_SUB/INTERVAL 的方言差异）。</p>
     *
     * @param userId    用户ID
     * @param startDate 统计起始时间（含）
     * @return 每天一行的 {@link DailyCostDTO}（按日期升序）
     */
    List<DailyCostDTO> selectDailyCostByUser(@Param("userId") Long userId, @Param("startDate") LocalDateTime startDate);

    /**
     * 统计某租户在时间范围内的总成本。
     *
     * @param tenantId  租户ID
     * @param startDate 起始时间（含）
     * @param endDate   结束时间（含）
     * @return total_cost / total_tokens / total_requests
     */
    Map<String, Object> selectTotalCostByTenant(
            @Param("tenantId") Long tenantId,
            @Param("startDate") LocalDateTime startDate,
            @Param("endDate") LocalDateTime endDate);

    /**
     * 统计某用户在时间范围内的总成本。
     *
     * @param userId    用户ID
     * @param startDate 起始时间（含）
     * @param endDate   结束时间（含）
     * @return total_cost / total_tokens / total_requests
     */
    Map<String, Object> selectTotalCostByUser(
            @Param("userId") Long userId,
            @Param("startDate") LocalDateTime startDate,
            @Param("endDate") LocalDateTime endDate);

    /**
     * 按模型分组的成本明细（支持按用户或按租户，二者可同时传入）。
     *
     * @param tenantId  租户ID（可为 null）
     * @param userId    用户ID（可为 null）
     * @param startDate 起始时间（含）
     * @param endDate   结束时间（含）
     * @return 每模型一行：model / request_count / total_tokens / total_cost
     */
    List<Map<String, Object>> selectCostBreakdown(
            @Param("tenantId") Long tenantId,
            @Param("userId") Long userId,
            @Param("startDate") LocalDateTime startDate,
            @Param("endDate") LocalDateTime endDate);
}
