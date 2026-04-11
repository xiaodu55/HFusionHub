package com.hfusionhub.config;

import cn.hutool.crypto.digest.BCrypt;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.entity.Tenant;
import com.hfusionhub.entity.TenantMember;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.TenantMapper;
import com.hfusionhub.mapper.TenantMemberMapper;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.tenant.TenantContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

/**
 * Creates or updates the admin user and default tenant on first startup.
 *
 * <p>If {@code ADMIN_PASSWORD} is not set, admin creation is skipped.
 * A default tenant (id=1, slug=default) is always ensured so existing
 * single-user deployments continue to work.</p>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class AdminInitializer implements ApplicationRunner {

    private final UserMapper userMapper;
    private final TenantMapper tenantMapper;
    private final TenantMemberMapper tenantMemberMapper;

    @Value("${app.admin.username:admin}")
    private String adminUsername;

    @Value("${app.admin.password:}")
    private String adminPassword;

    @Override
    public void run(ApplicationArguments args) {
        // Run as system scope to bypass tenant-line interceptor during bootstrapping.
        // The tenant and user tables are cross-tenant resources that must be
        // accessible before any tenant context exists.
        TenantContext.runAsSystem(() -> {
            // Ensure default tenant exists (for backward compat)
            ensureDefaultTenant();

            // Create/update admin user
            if (adminPassword == null || adminPassword.isBlank()) {
                log.warn("ADMIN_PASSWORD is not set. Admin user will NOT be created. "
                        + "Set the ADMIN_PASSWORD environment variable to bootstrap the admin account.");
                return;
            }

            User admin = userMapper.selectOne(
                    new LambdaQueryWrapper<User>().eq(User::getUsername, adminUsername));

            if (admin == null) {
                admin = new User();
                admin.setUsername(adminUsername);
                admin.setPassword(BCrypt.hashpw(adminPassword));
                admin.setNickname("Administrator");
                admin.setRole(CommonConstants.ROLE_ADMIN);
                admin.setStatus(0);
                admin.setTenantId(1L);
                admin.setPlatformAdmin(true);
                userMapper.insert(admin);
                log.info("Admin user '{}' created (platform admin, tenant=1).", adminUsername);
            } else {
                // Ensure existing admin has platform_admin flag
                if (!Boolean.TRUE.equals(admin.getPlatformAdmin())) {
                    admin.setPlatformAdmin(true);
                    userMapper.updateById(admin);
                }
                if (!BCrypt.checkpw(adminPassword, admin.getPassword())) {
                    admin.setPassword(BCrypt.hashpw(adminPassword));
                    userMapper.updateById(admin);
                    log.info("Admin user '{}' password updated from ADMIN_PASSWORD.", adminUsername);
                } else {
                    log.info("Admin user '{}' already configured correctly.", adminUsername);
                }
            }
        });
    }

    private void ensureDefaultTenant() {
        Tenant defaultTenant = tenantMapper.selectById(1L);
        if (defaultTenant == null) {
            defaultTenant = new Tenant();
            defaultTenant.setName("默认租户");
            defaultTenant.setSlug("default");
            defaultTenant.setPlanTier("enterprise");
            defaultTenant.setStatus("active");
            tenantMapper.insert(defaultTenant);
            log.info("Default tenant created (id=1, slug=default).");
        }
    }
}
