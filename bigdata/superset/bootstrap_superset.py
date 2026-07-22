#!/usr/bin/env python3
"""HFusionData Analytics — Superset 看板一键引导(幂等)。

创建 2 个数据库连接、6 个数据集、6 张图表、6 个看板(5 张 ADS 口径 + 1 张
ClickHouse 实时窗口)。已存在的同名对象直接复用,重复执行安全。

前置(见 bigdata/superset/README.md):
  1. superset db upgrade / fab create-admin / superset init 已完成
  2. 容器内已 pip install clickhouse-connect(阿里云源)
  3. 环境变量: SUPSET_PASSWORD(管理员密码,与 docker/.env ADMIN_PASSWORD 一致)、
     MYSQL_PASSWORD(ADS 镜像读取)、CLICKHOUSE_PASSWORD

用法(宿主机):
  python bootstrap_superset.py
"""

from __future__ import annotations

import json
import os
import urllib.request

BASE = os.environ.get("SUPERSET_URL", "http://localhost:8088")
ADMIN_PW = os.environ["SUPERSET_PASSWORD"]
MYSQL_PW = os.environ["MYSQL_PASSWORD"]
CH_PW = os.environ.get("CLICKHOUSE_PASSWORD", "analytics123")


_CSRF = {"token": None}


def api(token: str, method: str, path: str, payload: dict | None = None) -> dict:
    import json

    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Referer", BASE)
    if method in ("POST", "PUT", "DELETE") and _CSRF["token"]:
        req.add_header("X-CSRFToken", _CSRF["token"])
    # 本机代理(如 Clash 7890)会劫持 localhost 请求返回 404 —— 显式绕过
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        print(f"  [debug] {method} {req.full_url} -> {e.code}; body={e.read()[:200]!r}")
        raise


def fetch_csrf(token: str) -> None:
    # Superset 对写操作强制 CSRF:令牌经 GET /api/v1/security/csrf/ 下发。
    # 本仓库 superset_config.py 已关闭 WTF_CSRF(开发口径),端点可能 404 —— 容错跳过。
    try:
        _CSRF["token"] = api(token, "GET", "/api/v1/security/csrf/")["result"]
        print("[ok] CSRF 令牌已获取")
    except Exception:
        print("[info] CSRF 端点不可用(WTF_CSRF_ENABLED=False 时无需令牌),继续")


def login() -> str:
    resp = api("", "POST", "/api/v1/security/login",
               {"username": "admin", "password": ADMIN_PW,
                "provider": "db", "refresh": True})
    return resp["access_token"]


def find_by_name(token: str, kind: str, name: str) -> int | None:
    import json
    from urllib.parse import quote

    filters = {"database": ("database_name", "database/"),
               "dataset": ("table_name", "dataset/"),
               "chart": ("slice_name", "chart/"),
               "dashboard": ("dashboard_title", "dashboard/")}
    col, path = filters[kind]
    # rison 结构字符(())!:,' 必须原样保留,仅编码空格/中文等;全量 quote 会让 FAB 解析失败返回 404
    rison = quote(f"(filters:!((col:{col},opr:eq,value:'{name}')))", safe="()!:,'")
    resp = api(token, "GET", f"/api/v1/{path}?q={rison}")
    result = resp.get("result", [])
    return result[0]["id"] if result else None


def create_if_absent(token: str, kind: str, name: str, payload: dict) -> int:
    existing = find_by_name(token, kind, name)
    if existing:
        print(f"  [skip] {kind} '{name}' 已存在 id={existing}")
        return existing
    resp = api(token, "POST", f"/api/v1/{ {'database': 'database/', 'dataset': 'dataset/', 'chart': 'chart/', 'dashboard': 'dashboard/'}[kind] }",
               {**payload, **({} if kind == "dataset" else {})})
    rid = resp.get("id")
    print(f"  [create] {kind} '{name}' id={rid}")
    return rid


def main() -> int:
    token = login()
    print("[ok] Superset 登录成功")
    fetch_csrf(token)

    # ── 数据库连接 ────────────────────────────────────────────────────────
    mysql_db = create_if_absent(token, "database", "HFusionData MySQL ADS", {
        "database_name": "HFusionData MySQL ADS",
        "sqlalchemy_uri": f"mysql://hfusionhub:{MYSQL_PW}@mysql8:3306/hfusionhub",
        "expose_in_sqllab": True,
    })
    ch_db = create_if_absent(token, "database", "HFusionData ClickHouse", {
        "database_name": "HFusionData ClickHouse",
        "sqlalchemy_uri": f"clickhousedb+connect://analytics:{CH_PW}@analytics-clickhouse:8123/analytics",
        "expose_in_sqllab": True,
    })

    # ── 数据集 ────────────────────────────────────────────────────────────
    # realtime_metrics 显式带 schema:clickhousedb+connect 方言的反射不带
    # URI 里的默认库,不指定 schema 会报 422 "Table could not be found"。
    datasets = {
        "ads_cost_daily": (mysql_db, None),
        "ads_model_share": (mysql_db, None),
        "ads_tenant_topn": (mysql_db, None),
        "ads_tool_success": (mysql_db, None),
        "ads_eval_quality": (mysql_db, None),
        "realtime_metrics": (ch_db, "analytics"),
    }
    ds_ids = {}
    for table, (db_id, schema) in datasets.items():
        try:
            ds_ids[table] = create_if_absent(
                token, "dataset", table,
                {"database": db_id, "table_name": table, "schema": schema})
        except Exception as exc:
            print(f"  [warn] 数据集 '{table}' 创建失败({exc}),跳过——看板其余部分继续")
            ds_ids[table] = None

    # ── 图表(name, viz_type, dataset, params 骨架) ────────────────────────
    def metric(col, agg):
        return {"expressionType": "SIMPLE", "column": {"column_name": col},
                "aggregate": agg, "label": f"{agg}({col})"}

    charts = [
        ("成本趋势(日)", "echarts_timeseries_bar", "ads_cost_daily",
         {"x_axis": "stat_date", "metrics": [metric("cost_usd", "SUM"), metric("call_count", "SUM")],
          "groupby": [], "x_axis_sort_asc": True}),
        ("模型成本占比", "pie", "ads_model_share",
         {"metrics": [metric("cost_usd", "SUM")], "groupby": ["model"]}),
        ("租户成本 TopN", "echarts_timeseries_bar", "ads_tenant_topn",
         {"x_axis": "rank_no", "metrics": [metric("cost_usd", "SUM")], "groupby": ["tenant_id"],
          "orientation": "horizontal"}),
        ("Agent 步骤成功率", "table", "ads_tool_success",
         {"metrics": [metric("success_rate", "AVG"), metric("step_count", "SUM")], "groupby": ["step_type"]}),
        ("评测质量趋势", "echarts_timeseries_line", "ads_eval_quality",
         {"x_axis": "stat_date", "metrics": [metric("avg_hit_ratio", "AVG"), metric("failure_rate", "AVG")],
          "groupby": []}),
        ("实时请求窗口", "echarts_timeseries_line", "realtime_metrics",
         {"x_axis": "window_start", "metrics": [metric("request_count", "SUM"), metric("total_tokens", "SUM")],
          "groupby": []}),
    ]
    chart_ids = []
    for name, viz, table, params in charts:
        ds_id = ds_ids.get(table)
        if ds_id is None:
            print(f"  [warn] 图表 '{name}' 的数据集缺失,跳过")
            chart_ids.append(None)
            continue
        payload = {
            "slice_name": name,
            "viz_type": viz,
            "datasource_id": ds_id,
            "datasource_type": "table",
            # params 必须是合法 JSON 字符串:python repr 的单引号会被拒
            "params": json.dumps({"datasource": f"{ds_id}__table", "viz_type": viz,
                                  "x_axis": params.get("x_axis"), "metrics": params.get("metrics"),
                                  "groupby": params.get("groupby"),
                                  "orientation": params.get("orientation")}),
        }
        chart_ids.append(create_if_absent(token, "chart", name, payload))

    # ── 看板 ──────────────────────────────────────────────────────────────
    dashboards = [
        ("HFusionData·成本趋势", [chart_ids[0]]),
        ("HFusionData·模型占比", [chart_ids[1]]),
        ("HFusionData·租户TopN(平台)", [chart_ids[2]]),
        ("HFusionData·步骤成功率", [chart_ids[3]]),
        ("HFusionData·评测质量", [chart_ids[4]]),
        ("HFusionData·实时窗口(ClickHouse)", [chart_ids[5]]),
    ]
    for name, slices in dashboards:
        slices = [s for s in slices if s]
        if not slices:
            print(f"  [warn] dashboard '{name}' 无可用图表,跳过")
            continue
        # Superset 4.0.1 的 REST API 不提供图表↔看板关联写路由(POST/PUT 均不收
        # slices 字段),dev 口径直接写元库 dashboard_slices 关联表。
        dash_id = create_if_absent(token, "dashboard", name,
                                   {"dashboard_title": name, "slug": None})
        current = api(token, "GET", f"/api/v1/dashboard/{dash_id}")
        linked = [s["id"] for s in current.get("result", {}).get("slices", [])]
        missing = [s for s in slices if s not in linked]
        if missing:
            import subprocess
            pairs = json.dumps(list(zip([dash_id] * len(missing), missing)))
            link_py = (
                "import sqlite3, json\n"
                "conn = sqlite3.connect('/app/superset_home/superset.db')\n"
                f"pairs = json.loads('{pairs}')\n"
                "for dash, chart in pairs:\n"
                "    conn.execute('INSERT OR IGNORE INTO dashboard_slices "
                "(dashboard_id, slice_id) VALUES (?, ?)', (dash, chart))\n"
                "conn.commit()\n"
                "print('linked', conn.total_changes)\n"
            )
            subprocess.run(["docker", "exec", "analytics-superset", "python3", "-c", link_py],
                           check=True, capture_output=True, text=True)
            print(f"  [link] dashboard '{name}' charts={missing} (元库直写)")
        else:
            print(f"  [link] dashboard '{name}' 已关联 slices={linked}")

    print("[done] Superset 看板引导完成 → http://localhost:8088")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
