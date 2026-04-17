-- New registrations must be approved by the sole platform super admin.
ALTER TABLE `sys_user`
    MODIFY COLUMN `role` VARCHAR(20) NOT NULL DEFAULT 'pending'
    COMMENT '平台身份：pending-待分配，user-普通用户，builder-AI配置员，admin-唯一超级管理员';

-- Preserve the configured built-in admin account as the sole super admin.
UPDATE `sys_user`
SET `role` = 'builder', `platform_admin` = 0
WHERE (`role` = 'admin' OR `platform_admin` = 1)
  AND `username` <> 'admin';

UPDATE `sys_user`
SET `role` = 'admin', `platform_admin` = 1
WHERE `username` = 'admin';
