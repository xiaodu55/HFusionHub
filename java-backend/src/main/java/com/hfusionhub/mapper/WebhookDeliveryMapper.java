package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.WebhookDelivery;
import org.apache.ibatis.annotations.Mapper;

/**
 * Webhook 投递记录 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface WebhookDeliveryMapper extends BaseMapper<WebhookDelivery> {}
