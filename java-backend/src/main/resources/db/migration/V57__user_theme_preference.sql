-- V57: 用户界面主题偏好（light | dark | system），用于主题服务端同步
ALTER TABLE sys_user ADD COLUMN theme_preference VARCHAR(16) DEFAULT NULL;
