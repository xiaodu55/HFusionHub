package com.hfusionhub.scheduler;

import com.hfusionhub.common.lock.SchedulerLock;
import com.hfusionhub.service.impl.AnalyticsBatchRunner;
import java.time.LocalDate;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 大数据日结调度 — 每日 04:00 触发 全量导入 → DWD → DWS → 质量门禁 → ADS。
 *
 * <p>默认关闭(bigdata.batch.enabled=false):分析扩展包未部署时零行为。
 * 启用后命令模板经 bigdata.batch.jobs.* 注入;@SchedulerLock 保证多实例
 * 单次执行(与主产品调度器同一把锁机制)。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class BigDataBatchScheduler {

    private final AnalyticsBatchRunner batchRunner;

    @Value("${bigdata.batch.enabled:false}")
    private boolean enabled;

    @Value("${bigdata.batch.offset-days:1}")
    private int offsetDays;

    @Scheduled(cron = "${bigdata.batch.cron:0 0 4 * * ?}")
    @SchedulerLock("bigdata-batch")
    public void runDailyBatch() {
        if (!enabled) {
            log.debug("Analytics batch disabled (bigdata.batch.enabled=false), skip");
            return;
        }
        LocalDate batchDate = LocalDate.now().minusDays(Math.max(1, offsetDays));
        log.info("[analytics-batch] 日结开始 dt={}", batchDate);
        batchRunner.runPipeline(batchDate, null);
        log.info("[analytics-batch] 日结结束 dt={}", batchDate);
    }
}
