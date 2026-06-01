package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.TenantPlanBinding;
import org.apache.ibatis.annotations.Mapper;

/**
 * 租户套餐绑定 Mapper（招投标垂直化 · P2）
 *
 * @author HFusionHub Team
 */
@Mapper
public interface TenantPlanBindingMapper extends BaseMapper<TenantPlanBinding> {
}
