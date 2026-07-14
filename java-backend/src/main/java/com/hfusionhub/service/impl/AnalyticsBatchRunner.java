package com.hfusionhub.service.impl;

import com.hfusionhub.entity.BigDataBatchRunLog;
import com.hfusionhub.mapper.BigDataBatchRunLogMapper;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * 大数据批处理执行器 — 调度器与手工回补共用。
 *
 * <p>命令模板来自配置(bigdata.batch.jobs.*),占位符 {date} 替换为处理日期。
 * 默认模板为空 = 该步骤 SKIPPED(分析扩展包未部署时主产品零行为)。
 * 每一步的执行记录落 bigdata_batch_run_log(RUNNING → SUCCESS/FAILED),
 * 质量门禁(quality-check)失败则阻断后续 ads-build,实现"不合格不下游"。</p>
 *
 * <p>示例模板(单机 compose,在 docs/BIGDATA_ARCHITECTURE.md 有完整版):
 * docker exec hadoop-client spark-submit --master yarn
 *   --jars /opt/bigdata/jars/mysql-connector-j-8.0.33.jar
 *   /opt/bigdata/spark-jobs/dwd_transform.py --dt {date}</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
public class AnalyticsBatchRunner {

    /** 可注入的命令执行器(测试用 fake 替换真实进程)。 */
    @FunctionalInterface
    public interface CommandExecutor {
        int execute(List<String> command, StringBuilder outputSink) throws Exception;
    }

    public static final String JOB_FULL_IMPORT = "full-import";
    public static final String JOB_DWD = "dwd-transform";
    public static final String JOB_DWS = "dws-aggregate";
    public static final String JOB_QUALITY = "quality-check";
    public static final String JOB_ADS = "ads-build";
    public static final String JOB_PIPELINE = "pipeline";

    private static final String[] PIPELINE_ORDER = {
            JOB_FULL_IMPORT, JOB_DWD, JOB_DWS, JOB_QUALITY, JOB_ADS};

    private static final int LOG_TAIL_CHARS = 1800;

    private final BigDataBatchRunLogMapper batchLogMapper;
    private final CommandExecutor executor;

    @Value("${bigdata.batch.jobs.full-import:}")
    private String fullImportCommand;

    @Value("${bigdata.batch.jobs.dwd-transform:}")
    private String dwdCommand;

    @Value("${bigdata.batch.jobs.dws-aggregate:}")
    private String dwsCommand;

    @Value("${bigdata.batch.jobs.quality-check:}")
    private String qualityCommand;

    @Value("${bigdata.batch.jobs.ads-build:}")
    private String adsCommand;

    @Autowired
    public AnalyticsBatchRunner(BigDataBatchRunLogMapper batchLogMapper) {
        this(batchLogMapper, defaultExecutor());
    }

    AnalyticsBatchRunner(BigDataBatchRunLogMapper batchLogMapper, CommandExecutor executor) {
        this.batchLogMapper = batchLogMapper;
        this.executor = executor;
    }

    static CommandExecutor defaultExecutor() {
        return (command, sink) -> {
            Process process = new ProcessBuilder(command)
                    .redirectErrorStream(true)
                    .start();
            try (InputStream in = process.getInputStream()) {
                byte[] buffer = in.readAllBytes();
                sink.append(new String(buffer, StandardCharsets.UTF_8));
            }
            return process.waitFor();
        };
    }

    private String templateFor(String jobName) {
        return switch (jobName) {
            case JOB_FULL_IMPORT -> fullImportCommand;
            case JOB_DWD -> dwdCommand;
            case JOB_DWS -> dwsCommand;
            case JOB_QUALITY -> qualityCommand;
            case JOB_ADS -> adsCommand;
            default -> "";
        };
    }

    /**
     * 执行单步作业(命令模板 + {date} 替换)。返回执行记录 id;
     * 模板未配置时记 SKIPPED 并返回记录 id。
     */
    public Long runStep(String jobName, LocalDate date, Long tenantId) {
        BigDataBatchRunLog runLog = new BigDataBatchRunLog();
        runLog.setTenantId(tenantId);
        runLog.setJobName(jobName);
        runLog.setBatchDate(date);
        runLog.setStatus("RUNNING");
        runLog.setStartedAt(LocalDateTime.now());

        String template = templateFor(jobName);
        if (template == null || template.isBlank()) {
            runLog.setStatus("SKIPPED");
            runLog.setFinishedAt(LocalDateTime.now());
            runLog.setLogExcerpt("命令模板未配置(bigdata.batch.jobs." + jobName + "),跳过");
            batchLogMapper.insert(runLog);
            log.info("[analytics-batch] {} dt={} SKIPPED(未配置)", jobName, date);
            return runLog.getId();
        }

        String command = template.replace("{date}", date.toString());
        runLog.setCommand(command.length() > 1000 ? command.substring(0, 1000) : command);
        batchLogMapper.insert(runLog);

        StringBuilder output = new StringBuilder();
        int exit;
        try {
            List<String> argv = new ArrayList<>(Arrays.asList(command.trim().split("\\s+")));
            exit = executor.execute(List.copyOf(argv), output);
        } catch (Exception e) {
            exit = -1;
            output.append("\n[runner-error] ").append(e.getMessage());
        }

        runLog.setExitCode(exit);
        runLog.setStatus(exit == 0 ? "SUCCESS" : "FAILED");
        runLog.setFinishedAt(LocalDateTime.now());
        runLog.setDurationMs(Duration.between(runLog.getStartedAt(), runLog.getFinishedAt()).toMillis());
        String tail = output.length() > LOG_TAIL_CHARS
                ? output.substring(output.length() - LOG_TAIL_CHARS) : output.toString();
        runLog.setLogExcerpt(tail);
        batchLogMapper.updateById(runLog);
        log.info("[analytics-batch] {} dt={} exit={} durationMs={}",
                jobName, date, exit, runLog.getDurationMs());
        return runLog.getId();
    }

    /**
     * 执行完整日结管线:全量导入 → DWD → DWS → 质量门禁 →(通过后)ADS。
     * 任一步 FAILED 即中止后续(质量门禁失败阻断 ADS —— 不合格不下游)。
     */
    public List<Long> runPipeline(LocalDate date, Long tenantId) {
        BigDataBatchRunLog pipelineLog = new BigDataBatchRunLog();
        pipelineLog.setTenantId(tenantId);
        pipelineLog.setJobName(JOB_PIPELINE);
        pipelineLog.setBatchDate(date);
        pipelineLog.setStatus("RUNNING");
        pipelineLog.setStartedAt(LocalDateTime.now());
        batchLogMapper.insert(pipelineLog);

        List<Long> stepIds = new ArrayList<>();
        boolean failed = false;
        for (String job : PIPELINE_ORDER) {
            if (failed) {
                stepIds.add(recordSkipped(job, date, tenantId,
                        JOB_ADS.equals(job) && qualityStepRan(stepIds, date)
                                ? "质量门禁未通过,ADS 已阻断(不合格不下游)"
                                : "前序步骤失败,链路中止"));
                continue;
            }
            Long id = runStep(job, date, tenantId);
            stepIds.add(id);
            if (isFailed(id)) {
                failed = true;
            }
        }

        pipelineLog.setFinishedAt(LocalDateTime.now());
        pipelineLog.setDurationMs(Duration.between(
                pipelineLog.getStartedAt(), pipelineLog.getFinishedAt()).toMillis());
        pipelineLog.setStatus(failed ? "FAILED" : "SUCCESS");
        pipelineLog.setExitCode(failed ? 1 : 0);
        batchLogMapper.updateById(pipelineLog);
        return stepIds;
    }

    private boolean qualityStepRan(List<Long> stepIds, LocalDate date) {
        // pipeline 顺序固定: quality-check 是第 4 步(index 3)
        if (stepIds.size() < 4) {
            return false;
        }
        BigDataBatchRunLog qualityLog = batchLogMapper.selectById(stepIds.get(3));
        return qualityLog != null && "FAILED".equals(qualityLog.getStatus());
    }

    private boolean isFailed(Long runLogId) {
        BigDataBatchRunLog runLog = batchLogMapper.selectById(runLogId);
        return runLog == null || "FAILED".equals(runLog.getStatus());
    }

    private Long recordSkipped(String job, LocalDate date, Long tenantId, String reason) {
        BigDataBatchRunLog runLog = new BigDataBatchRunLog();
        runLog.setTenantId(tenantId);
        runLog.setJobName(job);
        runLog.setBatchDate(date);
        runLog.setStatus("SKIPPED");
        runLog.setStartedAt(LocalDateTime.now());
        runLog.setFinishedAt(LocalDateTime.now());
        runLog.setLogExcerpt(reason);
        batchLogMapper.insert(runLog);
        return runLog.getId();
    }
}
