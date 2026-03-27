package com.hfusionhub.service.impl;

import com.hfusionhub.dto.PromptTestCaseResult;
import com.hfusionhub.entity.PromptTestCaseResultEntity;
import com.hfusionhub.entity.PromptTestSetRun;
import com.hfusionhub.mapper.PromptTestCaseResultMapper;
import com.hfusionhub.mapper.PromptTestSetRunMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 提示词测试集批量运行的单用例「原子写」。
 *
 * <p>将「token 校验 + 进度更新 + 结果插入」封装为单个数据库事务：守卫更新
 * （token + 活跃状态）会对 run 行加排他锁，重试的 {@code retryRun} 需修改同一行
 * 因而与该事务互斥。若 run 已被取消→重试（token 重新生成）或由另一实例收敛，
 * 守卫更新命中 0 行，本方法立即返回 false，整个事务不写入任何结果——旧 Worker
 * 无法在「进度已写、结果未写」窗口残留脏数据。
 *
 * <p>作为独立 Spring bean（而非 {@link PromptTestSetServiceImpl} 的自调用），
 * 由调用方跨 bean 调用时 {@link Transactional} 代理生效，保证真正的事务边界。
 */
@Slf4j
@Service
public class PromptTestSetCaseWriter {

    /** 测试/可插拔窗口同步点：守卫更新成功（进度已写、未提交）后、结果插入前调用。生产环境为空。 */
    public interface CaseWriteHook {
        void onProgressWrittenBeforeInsert();
    }

    private final PromptTestSetRunMapper runMapper;
    private final PromptTestCaseResultMapper caseResultMapper;

    @Autowired(required = false)
    private CaseWriteHook caseWriteHook;

    public PromptTestSetCaseWriter(PromptTestSetRunMapper runMapper,
                                   PromptTestCaseResultMapper caseResultMapper) {
        this.runMapper = runMapper;
        this.caseResultMapper = caseResultMapper;
    }

    /**
     * 在单个事务内：守卫更新进度（token 校验）→ 插入用例结果。
     *
     * @return true 表示本次写入已提交；false 表示 run 已失效（token 变化或状态离开
     *         活跃集合），Worker 应中止且不得继续执行后续用例。
     */
    @Transactional(propagation = Propagation.REQUIRED)
    public boolean persistCase(PromptTestSetRun run, String token, int newProgress,
                               PromptTestCaseResult result) {
        Long runId = run.getId();
        int updated = runMapper.update(null, PromptTestSetRunGuards.activeRunGuard(runId, token)
                .set(PromptTestSetRun::getProgressCount, newProgress));
        if (updated == 0) {
            log.info("Prompt test set run {} stale — atomic case write rejected, worker aborts", runId);
            return false;
        }
        run.setProgressCount(newProgress);
        if (caseWriteHook != null) {
            caseWriteHook.onProgressWrittenBeforeInsert();
        }
        insertResult(runId, token, result);
        return true;
    }

    private void insertResult(Long runId, String token, PromptTestCaseResult r) {
        PromptTestCaseResultEntity entity = new PromptTestCaseResultEntity();
        entity.setRunId(runId);
        entity.setCaseId(r.getCaseId());
        entity.setQuestion(r.getQuestion());
        entity.setRenderedTemplate(r.getRenderedTemplate());
        entity.setContent(r.getContent());
        entity.setModel(r.getModel());
        entity.setTokenCount(r.getTokenCount());
        entity.setTokenUsage(r.getTokenUsage());
        entity.setSources(r.getSources());
        entity.setElapsedMs(r.getElapsedMs());
        entity.setSuccess(r.isSuccess());
        entity.setPassed(r.isPassed());
        entity.setPassNotes(r.getPassNotes());
        entity.setError(r.getError());
        entity.setExecutionToken(token);
        caseResultMapper.insert(entity);
    }
}
