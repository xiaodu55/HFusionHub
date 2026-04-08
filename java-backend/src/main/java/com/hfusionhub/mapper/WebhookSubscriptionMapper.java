package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.WebhookSubscription;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/**
 * Webhook 订阅配置 Mapper
 *
 * @author HFusionHub Team
 */
@Mapper
public interface WebhookSubscriptionMapper extends BaseMapper<WebhookSubscription> {

    /**
     * 查询订阅了指定事件且处于启用状态的订阅。
     * 事件列表以 JSON 数组存储，采用精确串匹配（前后带引号）避免误命中。
     * 租户行拦截器自动附加 tenant_id 隔离条件。
     *
     * @param eventType 事件类型
     * @return 启用中的订阅列表
     */
    List<WebhookSubscription> selectActiveByEvent(@Param("eventType") String eventType);
}
