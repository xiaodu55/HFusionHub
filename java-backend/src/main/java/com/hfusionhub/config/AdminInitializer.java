package com.hfusionhub.config;

import cn.hutool.crypto.digest.BCrypt;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.constant.CommonConstants;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.UserMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

/**
 * Creates or updates the admin user on first startup using the
 * {@code ADMIN_PASSWORD} environment variable.
 *
 * <p>If {@code ADMIN_PASSWORD} is not set, admin creation is skipped and a
 * warning is logged.  The V5 Flyway migration removes the default
 * historical default administrator account, so a fresh deployment will have no admin
 * user until this runner is supplied with a password.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class AdminInitializer implements ApplicationRunner {

    private final UserMapper userMapper;

    @Value("${app.admin.username:admin}")
    private String adminUsername;

    @Value("${app.admin.password:}")
    private String adminPassword;

    @Override
    public void run(ApplicationArguments args) {
        if (adminPassword == null || adminPassword.isBlank()) {
            log.warn("ADMIN_PASSWORD is not set. Admin user will NOT be created. "
                    + "Set the ADMIN_PASSWORD environment variable to bootstrap the admin account.");
            return;
        }

        User admin = userMapper.selectOne(
                new LambdaQueryWrapper<User>().eq(User::getUsername, adminUsername));

        if (admin == null) {
            // First run — create admin user
            admin = new User();
            admin.setUsername(adminUsername);
            admin.setPassword(BCrypt.hashpw(adminPassword));
            admin.setNickname("Administrator");
            admin.setRole(CommonConstants.ROLE_ADMIN);
            admin.setStatus(0);
            userMapper.insert(admin);
            log.info("Admin user '{}' created from ADMIN_PASSWORD.", adminUsername);
        } else if (!BCrypt.checkpw(adminPassword, admin.getPassword())) {
            // Password changed via environment — update it
            admin.setPassword(BCrypt.hashpw(adminPassword));
            userMapper.updateById(admin);
            log.info("Admin user '{}' password updated from ADMIN_PASSWORD.", adminUsername);
        } else {
            log.info("Admin user '{}' already configured correctly.", adminUsername);
        }
    }
}
