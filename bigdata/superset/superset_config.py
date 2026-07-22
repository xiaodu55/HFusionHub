# HFusionData Analytics — Superset 配置
# 挂载为 /app/pythonpath/superset_config.py(apache/superset 镜像约定)
# 首启初始化见同目录 README.md

import os

# 密钥由 compose 注入(部署时必须轮换,勿用默认值)
SUPERSET_SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "please-rotate-this-analytics-secret")

# SQLite 元库(单机演示;集群档换 PostgreSQL:
#   SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://user:pass@host/superset")
SQLALCHEMY_DATABASE_URI = "sqlite:////app/superset_home/superset.db"

# 功能开关:启用 SQL Lab 直查 Hive/ClickHouse
FEATURE_FLAGS = {
    "ENABLE_TEMPLATE_PROCESSING": True,
    "SQLLAB": True,
}

# 中文界面
LOCALES_PATH = "/app/superset/translations"
LANGUAGES = {
    "zh": {"flag": "cn", "name": "简体中文"},
    "en": {"flag": "us", "name": "English"},
}

# Hive 数据源连接串(在 Superset UI 建库时可直接参考):
#   hive://hive-server2:10000/hfusionhub        (impyla/thrift,鉴权 NONE)
# ClickHouse(标准档):
#   clickhousedb+connect://analytics:***@analytics-clickhouse:8123/analytics
# 生产建议:为 Superset 建只读账号,并在 Hive 侧行列级权限(Ranger)收敛。

# 开发环境(端口仅绑 127.0.0.1)关闭 CSRF:bootstrap_superset.py 经 REST API
# 批量建看板,而 4.0.1 部署里 /api/v1/security/csrf/ 端点未注册,写操作会被
# "The CSRF token is missing." 拦截。生产/集群档必须移除此项。
WTF_CSRF_ENABLED = False

