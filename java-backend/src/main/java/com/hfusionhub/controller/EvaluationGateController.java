package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.GateResult;
import com.hfusionhub.entity.AgentEvaluationRun;
import com.hfusionhub.entity.EvaluationGateResult;
import com.hfusionhub.service.AgentEvaluationService;
import com.hfusionhub.service.EvaluationGateService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 评测回归门禁控制器
 *
 * @author HFusionHub Team
 */
@RestController
@RequestMapping("/evaluation")
@RequiredArgsConstructor
@Tag(name = "评测回归门禁", description = "评测执行与回归门禁检查")
public class EvaluationGateController {

    private final AgentEvaluationService agentEvaluationService;
    private final EvaluationGateService evaluationGateService;

    /**
     * 执行一次评测并对最新结果进行回归门禁检查。
     */
    @PostMapping("/{datasetId}/gate")
    @Operation(summary = "执行评测并返回回归门禁结果")
    public R<GateResult> runGate(@PathVariable Long datasetId) {
        Long userId = JwtUtils.getCurrentUserId();
        AgentEvaluationRun run = agentEvaluationService.runEvaluation(datasetId, userId);
        GateResult gateResult = evaluationGateService.checkGate(userId, datasetId, run.getId());
        return R.ok(gateResult);
    }

    /**
     * 评测集的门禁通过/失败历史。
     */
    @GetMapping("/{datasetId}/gate-history")
    @Operation(summary = "评测门禁通过/失败历史")
    public R<List<EvaluationGateResult>> gateHistory(@PathVariable Long datasetId,
                                                     @RequestParam(defaultValue = "1") int page,
                                                     @RequestParam(defaultValue = "20") int pageSize) {
        Long userId = JwtUtils.getCurrentUserId();
        return R.ok(evaluationGateService.gateHistory(userId, datasetId, page, pageSize));
    }
}
