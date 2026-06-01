package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.BidSubscription;
import org.apache.ibatis.annotations.Mapper;

/**
 * 订阅套餐目录 Mapper（招投标垂直化 · P2）
 *
 * @author HFusionHub Team
 */
@Mapper
public interface BidSubscriptionMapper extends BaseMapper<BidSubscription> {
}
