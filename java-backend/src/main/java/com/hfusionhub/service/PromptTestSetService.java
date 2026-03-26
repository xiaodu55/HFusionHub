package com.hfusionhub.service;

import com.hfusionhub.dto.PromptTestCaseDTO;
import com.hfusionhub.dto.PromptTestCaseSaveDTO;
import com.hfusionhub.dto.PromptTestSetCompareRequest;
import com.hfusionhub.dto.PromptTestSetCompareResponse;
import com.hfusionhub.dto.PromptTestSetDTO;
import com.hfusionhub.dto.PromptTestSetDetailDTO;
import com.hfusionhub.dto.PromptTestSetRunDetailDTO;
import com.hfusionhub.dto.PromptTestSetRunDTO;
import com.hfusionhub.dto.PromptTestSetRunResponse;
import com.hfusionhub.dto.PromptTestSetRunRequest;
import com.hfusionhub.dto.PromptTestSetRunStatusDTO;
import com.hfusionhub.dto.PromptTestSetSaveDTO;
import com.hfusionhub.entity.PromptTestSetRun;

import java.util.List;

/** 提示词测试用例集服务 — 保存固定问题与变量值，批量运行同一组问题。 */
public interface PromptTestSetService {

    List<PromptTestSetDTO> listMine();

    PromptTestSetDetailDTO create(PromptTestSetSaveDTO dto);

    PromptTestSetDetailDTO getDetail(Long id);

    PromptTestSetDetailDTO update(Long id, PromptTestSetSaveDTO dto);

    void delete(Long id);

    /** 在用例集中添加一个用例 */
    PromptTestCaseDTO addCase(Long setId, PromptTestCaseSaveDTO dto);

    /** 更新用例集中的一个用例 */
    PromptTestCaseDTO updateCase(Long setId, Long caseId, PromptTestCaseSaveDTO dto);

    /** 删除用例集中的一个用例 */
    void deleteCase(Long setId, Long caseId);

    /** 用同一模板批量运行用例集中的所有问题。异步入队，立即返回任务状态。 */
    PromptTestSetRunStatusDTO run(Long setId, PromptTestSetRunRequest request);

    /** Worker 执行主体：逐用例运行并增量持久化，结束时收敛到终态。幂等。 */
    PromptTestSetRunResponse executeRun(Long runId);

    /** 获取批量运行任务的实时状态（轮询进度） */
    PromptTestSetRunStatusDTO getRunStatus(Long runId);

    /** 取消排队中或执行中的批量运行任务 */
    PromptTestSetRunStatusDTO cancelRun(Long runId);

    /** 重新排队一个已失败/已取消的运行（清除旧结果，attempt+1） */
    PromptTestSetRunStatusDTO retryRun(Long runId);

    /** 列出当前可派发的排队运行（供 Worker 认领） */
    List<PromptTestSetRun> listQueuedRuns(int limit);

    /** 认领一个排队运行（pending→running，守卫更新）。成功返回 true。 */
    boolean claimRun(Long runId);

    /** 恢复扫描：将失联的 running 运行标记为 failed */
    int markStaleRunsFailed(long staleMinutes);

    /** 列出用例集的运行历史（新到旧） */
    List<PromptTestSetRunDTO> listRuns(Long setId);

    /** 获取一次运行的详情（含每个用例结果） */
    PromptTestSetRunDetailDTO getRunDetail(Long runId);

    /** 对比两次运行，逐用例给出回答/耗时/Token/成败 */
    PromptTestSetCompareResponse compare(PromptTestSetCompareRequest request);
}
