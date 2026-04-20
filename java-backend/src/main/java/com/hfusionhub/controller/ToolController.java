package com.hfusionhub.controller;

import com.hfusionhub.client.AiClient;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.mapper.AgentStepMapper;
import com.hfusionhub.tenant.TenantContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.*;

/**
 * 工具中心 — 展示 Agent 可调用的工具注册表与最近调用记录。
 *
 * <p>工具元数据来自 Python Tool Registry（通过 AiClient 透传），
 * 调用记录来自 MySQL agent_step 表。写入类工具仍需在 Agent 任务页
 * 走人工审批——此页面仅做展示，不含执行入口。</p>
 */
@Slf4j
@RestController
@RequestMapping("/tools")
@RequiredArgsConstructor
public class ToolController {

    private final AiClient aiClient;
    private final AgentStepMapper agentStepMapper;

    /**
     * 工具注册表 — 透传 Python Tool Registry 的完整元数据。
     *
     * <p>返回每个工具的：名称、用途、读/写风险等级、所需权限、
     * 超时限制、版本门控状态。数据不写死在前端。</p>
     */
    @GetMapping
    public R<Map<String, Object>> listTools() {
        Map<String, Object> registry = aiClient.getToolRegistry(TenantContext.requireTenantId());

        // If the Python side returned an error, still serve it gracefully
        if (registry.containsKey("error") && registry.get("tools") instanceof List<?> tools && tools.isEmpty()) {
            return R.ok("工具注册表暂时不可用", registry);
        }

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> tools = (List<Map<String, Object>>) registry.getOrDefault("tools", List.of());

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("tools", tools);
        result.put("total", tools.size());

        // Attach risk summary for the overview card
        long readOnlyCount = tools.stream()
                .filter(t -> "read_only".equals(t.get("risk_level")))
                .count();
        long readWriteCount = tools.stream()
                .filter(t -> "read_write".equals(t.get("risk_level")))
                .count();
        long externalCount = tools.stream()
                .filter(t -> "external".equals(t.get("risk_level")))
                .count();

        Map<String, Long> riskSummary = new LinkedHashMap<>();
        riskSummary.put("read_only", readOnlyCount);
        riskSummary.put("read_write", readWriteCount);
        riskSummary.put("external", externalCount);
        result.put("risk_summary", riskSummary);

        if (registry.containsKey("error")) {
            result.put("notice", registry.get("error"));
        }

        return R.ok(result);
    }

    /**
     * 最近工具调用记录 — 来自 agent_step（仅 tool_call 类型）。
     *
     * <p>按 agent_task.user_id 过滤当前登录用户，确保用户 A
     * 无法读取用户 B 的 Agent 问题与工具调用记录。</p>
     *
     * <p>每条记录包含：工具名、所属 Agent 任务及原始问题、
     * 耗时、成功/失败、失败原因摘要。按时间倒序，默认最近 20 条。</p>
     */
    @GetMapping("/calls")
    public R<Map<String, Object>> listRecentCalls(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {

        Long userId = JwtUtils.getCurrentUserId();

        int offset = Math.max(0, (page - 1)) * pageSize;
        int limit = Math.min(Math.max(pageSize, 1), 100);

        List<Map<String, Object>> rawCalls = agentStepMapper.selectRecentToolCalls(userId, limit, offset);
        int total = agentStepMapper.countToolCalls(userId);

        // Transform for frontend consumption
        List<Map<String, Object>> calls = new ArrayList<>();
        for (Map<String, Object> row : rawCalls) {
            Map<String, Object> call = new LinkedHashMap<>();
            call.put("id", row.get("id"));
            call.put("tool_name", row.get("tool_name"));
            call.put("duration_ms", row.get("duration_ms"));

            boolean isError = row.get("error_code") != null && !"".equals(row.get("error_code"));
            call.put("success", !isError);
            call.put("error_code", row.get("error_code"));
            call.put("error_summary", isError ? row.get("error_summary") : null);

            // Task context
            Map<String, Object> task = new LinkedHashMap<>();
            task.put("id", row.get("task_id"));
            task.put("query", row.get("task_query"));
            task.put("status", row.get("task_status"));
            call.put("task", task);

            call.put("created_at", row.get("created_at"));
            calls.add(call);
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("calls", calls);
        result.put("total", total);
        result.put("page", page);
        result.put("page_size", pageSize);
        result.put("has_more", offset + limit < total);

        return R.ok(result);
    }

    // ── MCP Client 管理（B5）───────────────────────────────────────────

    @GetMapping("/mcp/servers")
    public R<Map<String, Object>> listMcpServers() {
        return R.ok(aiClient.listMcpServers());
    }

    @PostMapping("/mcp/servers")
    public R<Map<String, Object>> addMcpServer(@RequestBody Map<String, Object> body) {
        Map<String, Object> result = aiClient.addMcpServer(body);
        boolean success = Boolean.TRUE.equals(result.get("success"));
        return success ? R.ok(String.valueOf(result.getOrDefault("message", "已添加")), result)
                : R.fail(String.valueOf(result.getOrDefault("message", "添加失败")));
    }

    @PostMapping("/mcp/servers/{serverId}/reconnect")
    public R<Map<String, Object>> reconnectMcpServer(@PathVariable String serverId) {
        Map<String, Object> result = aiClient.reconnectMcpServer(serverId);
        boolean success = Boolean.TRUE.equals(result.get("success"));
        return success ? R.ok(String.valueOf(result.getOrDefault("message", "已重连")), result)
                : R.fail(String.valueOf(result.getOrDefault("message", "重连失败")));
    }

    @DeleteMapping("/mcp/servers/{serverId}")
    public R<Map<String, Object>> removeMcpServer(@PathVariable String serverId) {
        Map<String, Object> result = aiClient.removeMcpServer(serverId);
        boolean success = Boolean.TRUE.equals(result.get("success"));
        return success ? R.ok(String.valueOf(result.getOrDefault("message", "已移除")), result)
                : R.fail(String.valueOf(result.getOrDefault("message", "移除失败")));
    }
}
