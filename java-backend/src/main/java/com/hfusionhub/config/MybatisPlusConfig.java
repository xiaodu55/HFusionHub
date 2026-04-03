package com.hfusionhub.config;

import com.baomidou.mybatisplus.annotation.DbType;
import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor;
import com.baomidou.mybatisplus.extension.plugins.inner.PaginationInnerInterceptor;
import com.baomidou.mybatisplus.extension.plugins.handler.TenantLineHandler;
import com.baomidou.mybatisplus.extension.plugins.inner.TenantLineInnerInterceptor;
import com.hfusionhub.tenant.TenantContext;
import net.sf.jsqlparser.expression.Expression;
import net.sf.jsqlparser.expression.LongValue;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Set;

/**
 * MyBatis Plus 配置 — 分页 + 多租户自动隔离
 *
 * @author HFusionHub Team
 */
@Configuration
public class MybatisPlusConfig {

    @Value("${hfusionhub.tenant.enabled:true}")
    private boolean tenantEnabled;

    /**
     * Global tables that do NOT have a tenant_id column.
     * The tenant-line interceptor skips these.
     */
    private static final Set<String> TENANT_IGNORE_TABLES = Set.of(
        "sys_user", "tenant", "tenant_member", "role_permission",
        "tool", "feature_flag", "feature_flag_rule", "feature_flag_audit_log",
        "system_notice", "notice_recipient", "flyway_schema_history"
    );

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
                    Long tenantId = TenantContext.getTenantId();
                    return new LongValue(tenantId != null ? tenantId : 1L);
                }

                @Override
                public String getTenantIdColumn() {
                    return "tenant_id";
                }

                @Override
                public boolean ignoreTable(String tableName) {
                    return TENANT_IGNORE_TABLES.contains(tableName);
                }
            });
            interceptor.addInnerInterceptor(tenantInterceptor);
        }

        interceptor.addInnerInterceptor(new PaginationInnerInterceptor(DbType.MYSQL));
        return interceptor;
    }
}
