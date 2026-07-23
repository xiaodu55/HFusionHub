#!/usr/bin/env python3
"""HFusionData Analytics — DolphinScheduler 日结流水线一键引导(幂等)。

创建项目 + 6 任务 SHELL 工作流(full-import → dwd → dws → quality(门禁)
→ ads → ch-sync),发布并按 --dt 触发一次验证。任务经 worker 容器内的
docker CLI 走 `docker exec analytics-spark` 提交(与 Java AnalyticsBatchRunner
同一命令模板;worker 挂载 docker.sock + 静态 docker CLI,见 compose 注释)。

前置:
  1. analytics-dolphinscheduler 已启动(标准档),UI http://localhost:12345
  2. worker 内 docker CLI 可用(compose 已挂载)
环境变量:
  MYSQL_PASSWORD —— 用于读取 docker/.env 之外无其他用途;dt 取 T-1 或显式 --dt

用法(宿主机):
  python bootstrap_dolphinscheduler.py [--dt 2026-09-02] [--no-run]
默认 dt = 昨天(与 BIGDATA_BATCH_OFFSET_DAYS=1 的 T-1 口径一致)。
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.cookiejar
import json
import os
import random
import time
import urllib.parse
import urllib.request

# 注意:3.2 standalone 的 API 基路径是 /dolphinscheduler(/ui 是前端静态资源,
# POST /ui/login 会 405)。登录口为 POST /dolphinscheduler/login(表单)。
BASE = os.environ.get("DS_URL", "http://localhost:12345/dolphinscheduler")
DS_USER = os.environ.get("DS_USER", "admin")
DS_PASSWORD = os.environ.get("DS_PASSWORD", "***REMOVED-BY-REWRITE***")

opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),  # 绕过本机代理(会劫持 localhost)
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
)


SESSION = {"id": None}


def call(method: str, path: str, payload: dict | None = None,
         form: bool = False) -> dict:
    url = BASE + path
    if form and payload:
        data = urllib.parse.urlencode(payload).encode()
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    elif payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
    else:
        req = urllib.request.Request(url, method=method)
    # DS UI API 的认证机制:登录返回的 sessionId 作为请求头携带
    if SESSION["id"]:
        req.add_header("sessionId", SESSION["id"])
    try:
        with opener.open(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  [debug] {method} {path} -> {e.code}; body={e.read()[:300]!r}")
        raise


def gen_code() -> int:
    """DS 任务码为 int64 雪花值;API 创建时用随机大整数保证唯一。"""
    return random.randint(10 ** 15, 10 ** 16 - 1)


SPARK_SUBMIT = (
    "docker exec analytics-spark /opt/spark/bin/spark-submit "
    "--master yarn --conf spark.driver.host=analytics-spark "
    "--conf spark.driver.bindAddress=0.0.0.0"
)

TASKS = [
    ("full-import", f"{SPARK_SUBMIT} --jars /opt/bigdata/jars/mysql-connector-j-8.0.33.jar "
                    f"/opt/bigdata/scripts/full_import.py --dt ${{dt}}"),
    ("dwd-transform", f"{SPARK_SUBMIT} /opt/bigdata/spark-jobs/dwd_transform.py --dt ${{dt}}"),
    ("dws-aggregate", f"{SPARK_SUBMIT} /opt/bigdata/spark-jobs/dws_aggregate.py --dt ${{dt}}"),
    ("quality-check", f"{SPARK_SUBMIT} /opt/bigdata/spark-jobs/quality_check.py --dt ${{dt}}"),
    ("ads-build", f"{SPARK_SUBMIT} --jars /opt/bigdata/jars/mysql-connector-j-8.0.33.jar "
                  f"/opt/bigdata/spark-jobs/ads_build.py --dt ${{dt}}"),
    ("ch-sync", f"{SPARK_SUBMIT} --driver-class-path /opt/bigdata/jars/clickhouse-jdbc-0.6.3-all.jar "
                f"--jars /opt/bigdata/jars/clickhouse-jdbc-0.6.3-all.jar,/opt/bigdata/jars/mysql-connector-j-8.0.33.jar "
                f"/opt/bigdata/spark-jobs/ch_sync.py"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap DolphinScheduler pipeline")
    parser.add_argument("--dt", default=(dt.date.today() - dt.timedelta(days=1)).isoformat(),
                        help="验证运行的数据日期(默认 T-1)")
    parser.add_argument("--no-run", action="store_true", help="只建工作流不触发")
    args = parser.parse_args()

    # ── 登录(sessionId 作为后续 API 调用的请求头) ─────────────────────────
    login = call("POST", "/login", {"userName": DS_USER, "userPassword": DS_PASSWORD}, form=True)
    assert login.get("code") == 0, f"登录失败: {login}"
    SESSION["id"] = login["data"]["sessionId"]
    print("[ok] DS 登录成功")

    # ── 项目(DS UI API 走表单编码) ─────────────────────────────────────────
    resp = call("POST", "/projects", {"projectName": "HFusionData",
                                      "description": "多租户 AI 平台运营数据分析"},
                form=True)
    if resp.get("code") == 0:
        project_code = resp["data"]["code"]
        print(f"  [create] 项目 HFusionData code={project_code}")
    else:
        print(f"  [warn] 项目创建返回: {resp}")
        projects = call("GET", "/projects/list")["data"]
        project_code = next(p["code"] for p in projects if p["name"] == "HFusionData")
        print(f"  [skip] 项目已存在 code={project_code}")

    # ── 工作流定义 ─────────────────────────────────────────────────────────
    task_list, relations = [], []
    prev_code = 0
    for name, script in TASKS:
        code = gen_code()
        task_list.append({
            "code": code, "name": name, "version": 0, "projectCode": project_code,
            "taskType": "SHELL",
            "taskParams": {"resourceList": [], "localParams": [],
                           "rawScript": script},
            "flag": "YES", "taskPriority": "MEDIUM", "workerGroup": "default",
            "failRetryTimes": 1, "failRetryInterval": 5, "timeoutFlag": "CLOSE",
            "timeoutNotifyStrategy": "", "timeout": 0, "delayTime": 0,
            "environmentCode": -1, "description": "",
            # transformTask 会逐个读取这些字段,缺 isCache/taskExecuteType 即
            # NPE(3.2.1 已知坑,isCache 为 DS 源码 1964 行 getIsCache().getCode())
            "isCache": "NO", "taskExecuteType": "BATCH", "cpuQuota": -1,
            "memoryMax": -1, "taskGroupId": 0, "taskGroupPriority": 0,
            "resourceIds": "",
        })
        relations.append({"name": "", "preTaskCode": prev_code, "preTaskVersion": 0,
                          "postTaskCode": code, "postTaskVersion": 0,
                          "conditionType": "NONE", "conditionParams": {}})
        prev_code = code

    # ── 工作流定义(此版本暴露的是旧式 process-definition 路由,且控制器全部
    #    走 @RequestParam 表单参数 —— JSON body 会被 10105 拒绝;
    #    taskDefinitionJson / taskRelationJson 为 JSON 字符串表单字段) ────────
    wf_name = "HFusionData-日结流水线"
    resp = call("POST", f"/projects/{project_code}/process-definition", {
        "name": wf_name,
        "description": "full-import → dwd → dws → quality(门禁,失败阻断下游) → ads → ch-sync",
        "globalParams": json.dumps([{"prop": "dt", "direct": "IN",
                                     "type": "VARCHAR", "value": args.dt}]),
        "locations": "[]",
        "timeout": "0",
        "taskDefinitionJson": json.dumps(task_list),
        "taskRelationJson": json.dumps(relations),
    }, form=True)
    if resp.get("code") == 0:
        wf_code = resp["data"]["code"]
        print(f"  [create] 工作流 code={wf_code}(6 任务链)")
    else:
        print(f"  [warn] 创建返回: {resp.get('msg')}(尝试复用同名工作流)")
        defs = call("GET", f"/projects/{project_code}/process-definition/list")["data"]
        items = defs["totalList"] if isinstance(defs, dict) else defs
        wf_code = None
        for w in items:
            pd = w.get("processDefinition", w)  # list 接口返回嵌套结构
            nm = pd.get("name")
            if nm == wf_name:
                wf_code = pd["code"]
                break
        if wf_code is None:
            print(f"  [debug] 列表形状: {json.dumps(items, ensure_ascii=False)[:300]}")
            raise SystemExit("无法定位同名工作流,请到 UI 检查")
        print(f"  [skip] 工作流已存在 code={wf_code}")

    # ── 发布 ───────────────────────────────────────────────────────────────
    call("POST", f"/projects/{project_code}/process-definition/{wf_code}/release",
         {"name": wf_name, "version": "0", "releaseState": "ONLINE"}, form=True)
    print("  [release] ONLINE")

    if args.no_run:
        print("[done] 工作流已发布(未触发)。UI: http://localhost:12345/dolphinscheduler/ui")
        return 0

    # ── 触发并轮询(此版本的启动路由是 start-process-instance,非文档的 start) ──
    call("POST", f"/projects/{project_code}/executors/start-process-instance", {
        "processDefinitionCode": str(wf_code), "scheduleCode": "",
        "failureStrategy": "END", "processInstancePriority": "MEDIUM",
        "workerGroup": "default",
        "globalParams": json.dumps([{"prop": "dt", "direct": "IN",
                                     "type": "VARCHAR", "value": args.dt}]),
        "startNodeList": "", "execType": "START_PROCESS",
        "commandType": "START_PROCESS", "taskDependType": "TASK_POST", "dryRun": "0",
    }, form=True)
    print(f"  [run] 已触发 dt={args.dt},轮询状态(六任务含 YARN 提交,预计 5-8 分钟)…")

    for _ in range(60):
        time.sleep(15)
        # 列表端点同样走普通查询参数(非 rison);按工作流名匹配最新实例
        r2 = call("GET", f"/projects/{project_code}/process-instances?pageNo=1&pageSize=10")
        items = (r2.get("data") or {})
        instances = items.get("totalList") if isinstance(items, dict) else items
        mine = [x for x in (instances or []) if x.get("name") == wf_name]
        if mine:
            inst = mine[0]
            state = inst["state"]
            print(f"  [poll] state={state}")
            if state in ("SUCCESS", "FAILURE", "STOP", "KILL"):
                if state == "SUCCESS":
                    print("[done] 日结流水线验证通过(SUCCESS)")
                    return 0
                print(f"[fail] 流水线结束于 {state};详情见 UI 的任务实例日志")
                return 1
    print("[fail] 轮询超时(15 分钟),请到 UI 查看进度")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
