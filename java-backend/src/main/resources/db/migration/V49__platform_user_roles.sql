-- Platform identities used by the role-aware frontend and backend guards.
ALTER TABLE `sys_user`
    MODIFY COLUMN `role` VARCHAR(20) NOT NULL DEFAULT 'user'
    COMMENT '平台身份：user-普通用户，builder-AI配置员，admin-系统管理员';

CREATE INDEX `idx_sys_user_role` ON `sys_user` (`role`);
