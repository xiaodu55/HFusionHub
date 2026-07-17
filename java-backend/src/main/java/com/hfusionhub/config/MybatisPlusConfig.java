package com.hfusionhub.config;

import com.baomidou.mybatisplus.annotation.DbType;
import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor;
import com.baomidou.mybatisplus.extension.plugins.handler.TenantLineHandler;
import com.baomidou.mybatisplus.extension.plugins.inner.PaginationInnerInterceptor;
import com.baomidou.mybatisplus.extension.plugins.inner.TenantLineInnerInterceptor;
import com.hfusionhub.tenant.TenantContext;
import java.util.Set;
import lombok.extern.slf4j.Slf4j;
import net.sf.jsqlparser.expression.Expression;
import net.sf.jsqlparser.expression.LongValue;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * MyBatis Plus 配置 — 分页 + 多租户自动隔离
 *
 * @author HFusionHub Team
 */
@Slf4j
@Configuration
public class MybatisPlusConfig {

    @Value("${hfusionhub.tenant.enabled:true}")
    private boolean tenantEnabled;

    /**
     * Global tables that do NOT have a tenant_id column.
     * The tenant-line interceptor skips these.
     */
    private static final Set<String> TENANT_IGNORE_TABLES = Set.of(
            "sys_user",
            "tenant",
            "tenant_member",
            "role_permission",
            "tool",
            "feature_flag",
            "feature_flag_rule",
            "feature_flag_audit_log",
            "system_notice",
            "notice_recipient",
            "flyway_schema_history",
            "tenant_audit_log",
            // Resource tables that predate tenant isolation and lack a tenant_id
            // column; they are reached only via a tenant-scoped parent and must not
            // be auto-filtered (the tenant-line interceptor would produce invalid
            // SQL referencing a non-existent column).
            "document_chunk",
            "document_index_job",
            "deletion_task",
            "prompt_template_version",
            "prompt_test_case",
            "prompt_test_case_result",
            "agent_status_event",
            "agent_recovery_event",
            "plugin_dependency",
            "plugin_execution_metric",
            "plugin_health_log",
            "plugin_version_history",
            // Evaluation tables — agent_evaluation_case and agent_evaluation_run
            // lack tenant_id; access is gated by dataset ownership (agent_evaluation_dataset
            // has tenant_id and is checked first).
            "agent_evaluation_case",
            "agent_evaluation_run",
            // Webhook delivery log — no tenant_id column; ownership resolved via
            // webhook_subscription (which has tenant_id and is tenant-filtered).
            "webhook_delivery",
            // Evaluation gate results — no tenant_id column; access is gated by
            // dataset ownership, same pattern as agent_evaluation_run.
            "evaluation_gate_result",
            // 订阅套餐目录（V69）——平台级目录，tenant_id 可空；租户查询须可见全目录，
            // 由服务层自行过滤租户自定义套餐，不走租户行拦截器。
            "bid_subscription",
            // 标书模板（V67）——tenant_id 可空 = 平台级模板（P2 行业方案包的基础）；
            // 租户查询须同时可见平台模板 + 自有模板，由服务层过滤，不走租户行拦截器。
            "bid_template",
            // 插件（V29+）——tenant_id 可空 = 平台内建插件（P2-3 bid_docx/bid_quote 上架基础）；
            // 租户查询须同时可见平台内建插件 + 自有插件，由服务层过滤，不走租户行拦截器。
            "plugin");

    /**
     * 分页 + 多租户插件
     */
    @Bean
    public MybatisPlusInterceptor mybatisPlusInterceptor() {
        MybatisPlusInterceptor interceptor = new MybatisPlusInterceptor();

        // Tenant-line interceptor — auto-appends WHERE tenant_id = ? to all queries.
        // Disabled in test profile via hfusionhub.tenant.enabled=false.
        if (tenantEnabled) {
            TenantLineInnerInterceptor tenantInterceptor = new TenantLineInnerInterceptor();
            tenantInterceptor.setTenantLineHandler(new TenantLineHandler() {
                @Override
                public Expression getTenantId() {
                    // Fail-closed: when no tenant context is set, return a
                    // sentinel (-1) that matches NO real tenant's rows.
                    // MyBatis Plus calls getTenantId() before ignoreTable(),
                    // so tables like sys_user (in TENANT_IGNORE_TABLES) would
                    // otherwise throw before ignoreTable can skip them — hence
                    // a sentinel instead of an exception. With the sentinel:
                    // context-less READs return nothing and context-less
                    // WRITEs stamp tenant_id=-1 (visible garbage, never
                    // another tenant's data). Legitimate context-less paths
                    // must opt in via TenantContext.runAsSystem() /
                    // runAs(); HTTP-layer isolation is enforced by
                    // TenantContextInterceptor (strict mode).
                    Long tenantId = TenantContext.getTenantId();
                    if (tenantId == null) {
                        log.warn("租户上下文缺失，SQL 已按 fail-closed 哨兵 tenant_id=-1 处理"
                                + "（如来自定时任务/异步线程，请用 TenantContext.runAs/runAsSystem 包裹）");
                        return new LongValue(-1);
                    }
                    return new LongValue(tenantId);
                }

                @Override
                public String getTenantIdColumn() {
                    return "tenant_id";
                }

                @Override
                public boolean ignoreTable(String tableName) {
                    // Cross-tenant maintenance tasks opt into system scope so
                    // their queries are NOT tenant-filtered.
                    if (TenantContext.isSystemScope()) {
                        return true;
                    }
                    return TENANT_IGNORE_TABLES.contains(tableName);
                }
            });
            interceptor.addInnerInterceptor(tenantInterceptor);
        }

        interceptor.addInnerInterceptor(new PaginationInnerInterceptor(DbType.MYSQL));
        return interceptor;
    }
}
