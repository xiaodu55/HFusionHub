-- ============================================================================
-- HFusionData Analytics — 01 建库
-- 提交: beeline -u jdbc:hive2://hive-server2:10000 -f 01_create_database.sql
-- 所有层的表都放在 hfusionhub 库下,物理路径 /warehouse/hfusionhub/<layer>/<table>
-- ============================================================================

CREATE DATABASE IF NOT EXISTS hfusionhub
  COMMENT 'HFusionHub AI 平台运营数仓(ODS/DIM/DWD/DWS/ADS 四层)'
  LOCATION '/warehouse/hfusionhub';

USE hfusionhub;
