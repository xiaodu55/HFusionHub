package com.hfusionhub.service.impl;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.hfusionhub.entity.BigDataBatchRunLog;
import com.hfusionhub.mapper.BigDataBatchRunLogMapper;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * AnalyticsBatchRunner 单元测试 — 命令模板/幂等日志/失败阻断管线。
 */
class AnalyticsBatchRunnerTest {

    private static final LocalDate DATE = LocalDate.of(2026, 8, 30);

    private BigDataBatchRunLogMapper batchLogMapper;
    private Map<Long, BigDataBatchRunLog> store;
    private AnalyticsBatchRunner runner;
    private final List<List<String>> executed = new java.util.ArrayList<>();

    @BeforeEach
    void setUp() {
        batchLogMapper = mock(BigDataBatchRunLogMapper.class);
        store = new HashMap<>();
        // 模拟 MyBatis 回填主键 + selectById 查库
        when(batchLogMapper.insert(any(BigDataBatchRunLog.class))).thenAnswer(inv -> {
            BigDataBatchRunLog log = inv.getArgument(0);
            long nextId = store.keySet().stream().mapToLong(Long::longValue).max().orElse(0) + 1;
            log.setId(nextId);
            store.put(nextId, log);
            return 1;
        });
        when(batchLogMapper.updateById(any(BigDataBatchRunLog.class))).thenAnswer(inv -> {
            BigDataBatchRunLog log = inv.getArgument(0);
            store.put(log.getId(), log);
            return 1;
        });
        when(batchLogMapper.selectById(any(Long.class))).thenAnswer(
                inv -> store.get(((Long) inv.getArgument(0))));

        executed.clear();
        AnalyticsBatchRunner.CommandExecutor executor = (command, sink) -> {
            executed.add(command);
            sink.append("fake-output");
            return 0;
        };
        runner = new AnalyticsBatchRunner(batchLogMapper, executor);
        ReflectionTestUtils.setField(runner, "fullImportCommand",
                "spark-submit full_import.py --dt {date}");
        ReflectionTestUtils.setField(runner, "dwdCommand",
                "spark-submit dwd_transform.py --dt {date}");
        ReflectionTestUtils.setField(runner, "dwsCommand",
                "spark-submit dws_aggregate.py --dt {date}");
        ReflectionTestUtils.setField(runner, "qualityCommand",
                "spark-submit quality_check.py --dt {date}");
        ReflectionTestUtils.setField(runner, "adsCommand",
                "spark-submit ads_build.py --dt {date}");
    }

    @Test
    void runStepSubstitutesDateAndRecordsSuccess() {
        Long id = runner.runStep(AnalyticsBatchRunner.JOB_FULL_IMPORT, DATE, null);

        assertThat(executed).hasSize(1);
        assertThat(String.join(" ", executed.get(0))).contains("--dt 2026-08-30");
        BigDataBatchRunLog log = store.get(id);
        assertThat(log.getStatus()).isEqualTo("SUCCESS");
        assertThat(log.getExitCode()).isEqualTo(0);
        assertThat(log.getDurationMs()).isNotNull();
    }

    @Test
    void emptyTemplateMarksSkippedWithoutExecuting() {
        ReflectionTestUtils.setField(runner, "fullImportCommand", "");

        Long id = runner.runStep(AnalyticsBatchRunner.JOB_FULL_IMPORT, DATE, null);

        assertThat(executed).isEmpty();
        BigDataBatchRunLog log = store.get(id);
        assertThat(log.getStatus()).isEqualTo("SKIPPED");
        assertThat(log.getLogExcerpt()).contains("未配置");
    }

    @Test
    void pipelineStopsOnStepFailure() {
        // 让 full-import 失败 → 后续步骤全部 SKIPPED
        runner = new AnalyticsBatchRunner(batchLogMapper, (command, sink) -> {
            executed.add(command);
            return String.join(" ", command).contains("full_import") ? 1 : 0;
        });
        ReflectionTestUtils.setField(runner, "fullImportCommand",
                "spark-submit full_import.py --dt {date}");
        ReflectionTestUtils.setField(runner, "dwdCommand",
                "spark-submit dwd_transform.py --dt {date}");
        ReflectionTestUtils.setField(runner, "dwsCommand",
                "spark-submit dws_aggregate.py --dt {date}");
        ReflectionTestUtils.setField(runner, "qualityCommand",
                "spark-submit quality_check.py --dt {date}");
        ReflectionTestUtils.setField(runner, "adsCommand",
                "spark-submit ads_build.py --dt {date}");

        List<Long> ids = runner.runPipeline(DATE, null);

        // stepIds = 5 步(full/dwd/dws/quality/ads);仅 full-import 真执行
        assertThat(ids).hasSize(5);
        assertThat(executed).hasSize(1);
        assertThat(store.get(ids.get(0)).getStatus()).isEqualTo("FAILED");
        assertThat(store.get(ids.get(1)).getStatus()).isEqualTo("SKIPPED");
        assertThat(store.get(ids.get(4)).getStatus()).isEqualTo("SKIPPED");
    }

    @Test
    void qualityFailureBlocksAdsBuild() {
        // 全部步骤执行,但 quality-check 退出 1 → ads-build 被阻断
        runner = new AnalyticsBatchRunner(batchLogMapper, (command, sink) -> {
            executed.add(command);
            return String.join(" ", command).contains("quality") ? 1 : 0;
        });
        ReflectionTestUtils.setField(runner, "fullImportCommand",
                "spark-submit full_import.py --dt {date}");
        ReflectionTestUtils.setField(runner, "dwdCommand",
                "spark-submit dwd_transform.py --dt {date}");
        ReflectionTestUtils.setField(runner, "dwsCommand",
                "spark-submit dws_aggregate.py --dt {date}");
        ReflectionTestUtils.setField(runner, "qualityCommand",
                "spark-submit quality_check.py --dt {date}");
        ReflectionTestUtils.setField(runner, "adsCommand",
                "spark-submit ads_build.py --dt {date}");

        List<Long> ids = runner.runPipeline(DATE, null);

        assertThat(executed).hasSize(4);   // full/dwd/dws/quality,ads 未执行
        assertThat(store.get(ids.get(3)).getStatus()).isEqualTo("FAILED");
        BigDataBatchRunLog adsLog = store.get(ids.get(4));
        assertThat(adsLog.getStatus()).isEqualTo("SKIPPED");
        assertThat(adsLog.getLogExcerpt()).contains("阻断");
        assertThat(store.get(ids.get(0)).getStatus()).isEqualTo("SUCCESS");
    }

    @Test
    void pipelineSucceedsWhenAllStepsPass() {
        List<Long> ids = runner.runPipeline(DATE, null);

        assertThat(ids).hasSize(5);
        assertThat(executed).hasSize(5);
        // 全部步骤 SUCCESS(状态落库由 updateById 覆盖)
        assertThat(store.values().stream()
                .filter(l -> !"pipeline".equals(l.getJobName()))
                .allMatch(l -> "SUCCESS".equals(l.getStatus()))).isTrue();
    }
}
