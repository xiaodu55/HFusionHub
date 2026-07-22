# HFusionData Analytics — Superset 部署与看板配置

## 0. 看板一键引导(推荐)

```bash
export SUPERSET_PASSWORD=<管理员密码,与 docker/.env ADMIN_PASSWORD 一致>
export MYSQL_PASSWORD=<docker/.env 的 MYSQL_PASSWORD>
python bigdata/superset/bootstrap_superset.py
```

幂等创建:2 个数据库连接(MySQL ADS 镜像 + ClickHouse)、6 个数据集、6 张图表、
6 个看板(成本趋势/模型占比/租户TopN/步骤成功率/评测质量/实时窗口)。
已存在的同名对象自动复用;需重建看板请先删除再重跑。

实现备注(Superset 4.0.1 的三个坑):
- 本机代理(Clash 等)会劫持 urllib 对 localhost 的请求,脚本内已用空 ProxyHandler 绕过;
- `POST/PUT /api/v1/dashboard` 均不接受 slices 字段,图表↔看板关联经元库
  `dashboard_slices` 表直写(dev 口径);
- `superset_config.py` 已关 `WTF_CSRF_ENABLED`(API 写操作需要,而该版本
  `/api/v1/security/csrf/` 端点未注册)。端口仅绑 127.0.0.1,生产必须移除。

## 1. 首启初始化

```bash
docker compose -f docker/docker-compose.analytics.yml --profile analytics up -d superset
# 初始化元库 + 创建管理员(按提示输入用户名密码)
docker exec -it analytics-superset superset db upgrade
docker exec -it analytics-superset superset fab create-admin \
  --username admin --firstname Admin --lastname Superset --password <强口令>
docker exec -it analytics-superset superset init
docker restart analytics-superset
```

访问 http://127.0.0.1:8088(仅回环)。

## 2. 数据源

| 数据源 | SQLAlchemy URI | 用途 |
|---|---|---|
| Hive 数仓 | `hive://hive-server2:10000/hfusionhub` | ADS/DWS 离线报表(日结) |
| ClickHouse(标准档) | `clickhousedb+connect://analytics:***@analytics-clickhouse:8123/analytics` | 实时指标高频查询 |

依赖:Superset 镜像自带 impyla/ thrift;ClickHouse 驱动需
`pip install clickhouse-connect`(可 exec 进容器安装后 restart)。

## 3. 建议看板(5 张,对应 ADS 口径)

1. **成本趋势** — `ads_cost_daily`:按日 cost_usd 柱状 + call_count 折线;
   过滤 `tenant_id = 登录租户`(平台管理员可看 -1 全局行)
2. **模型占比** — `ads_model_share`:cost_share 饼图 + 明细表
3. **租户 TopN**(平台管理员)— `ads_tenant_topn` 横条
4. **步骤成功率** — `ads_tool_success`:按 step_type 汇总 success_rate
5. **评测质量** — `ads_eval_quality`:avg_hit_ratio 趋势 + failure_rate

**多租户隔离**:普通用户场景建议用 Superset 的 RLS(Row Level Security)
规则 `tenant_id = {{ current_user_tenant() }}`(配合自定义 Jinja 宏从
JWT 取租户);本仓库默认由 Java 大屏页(/analytics)做服务端隔离,
Superset 仅供数据团队/管理员使用。
