#!/usr/bin/env python3
"""HFusionData Analytics — 合成数据制造器(百万级多租户运营事件)。

目的: 让离线/实时两条分析链路在演示与答辩时有真实量级与分布形态。
直接向 MySQL 业务表写数据,再由 full_import.py / Flink CDC 拉进数仓
—— 与真实业务数据同源同构。

FK 安全设计(全部显式分配 ID,不依赖 AUTO_INCREMENT 顺序):
  sys_user(合成,40 个,密码为不可登录占位哈希)
    └── conversation(合成会话,FK user_id)
          └── agent_task(FK user_id/conversation_id)
                └── agent_run(FK task_id)
                      └── agent_step(FK run_id)
  model_usage_record / usage_event 无外键,自由写入;
  agent 链路的 mur 行回填 agent_task_id 指向合成任务。

数据形态(--scale 默认 100 万,指 mur+usage_event 事件量):
  * 租户 1-8 权重递减(长尾分布);模型 4 种用量递减
  * 近 --days 天,日内双峰(10am/16pm)工作日偏置
  * token 对数正态;延迟右偏 + 2% 尖刺;错误率 ~2%
  * 账本幂等链: RESERVE -> COMMIT(94%) / RELEASE(6%)

用法:
  python seed_generator.py --password <db密码> [--scale 1000000 --days 30]
  python seed_generator.py --password *** --truncate   # 先清相关表
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import random
import sys

try:
    import pymysql
except ImportError:
    sys.exit("需要 pymysql: pip install pymysql")

MODELS = [("deepseek-v4-flash", 0.62), ("deepseek-chat", 0.20),
          ("deepseek-reasoner", 0.12), ("ollama-local", 0.06)]
REQUEST_TYPES = [("chat", 0.55), ("agent", 0.25), ("embedding", 0.15), ("evaluation", 0.05)]
TENANT_WEIGHTS = [0.30, 0.22, 0.16, 0.12, 0.09, 0.06, 0.03, 0.02]   # 租户 1..8
STEP_TYPES = [("intent_classification", 0.16), ("retrieval", 0.30),
              ("tool_call", 0.22), ("model_generation", 0.24),
              ("reflection", 0.05), ("grounding_check", 0.03)]
RUN_ERROR_CODES = [None] * 94 + ["timeout", "tool_error", "internal_error"]  # ~2% 错误
STEP_ERROR_CODES = [None] * 96 + ["timeout", "tool_error", "internal_error"]
N_USERS = 40          # 合成用户数(8 租户 × 5)
CONVS_PER_USER = 3
BATCH = 5000


def weighted(rng, items):
    r, acc = rng.random(), 0.0
    for value, weight in items:
        acc += weight
        if r <= acc:
            return value
    return items[-1][0]


def synth_time(rng, start: dt.date, days: int) -> dt.datetime:
    day = start - dt.timedelta(days=rng.randint(0, days - 1))
    if day.weekday() >= 5 and rng.random() < 0.5:      # 工作日偏置
        day = day - dt.timedelta(days=2)
    peak = 10 if rng.random() < 0.55 else 16           # 日内双峰
    hour = max(0, min(23, int(rng.gauss(peak, 2.4))))
    return dt.datetime(day.year, day.month, day.day, hour, rng.randint(0, 59), rng.randint(0, 59))


def lognormal_tokens(rng) -> int:
    return max(64, int(math.exp(rng.gauss(6.4, 1.0))))


def latency_ms(rng) -> int:
    base = int(math.exp(rng.gauss(7.2, 0.5)))
    if rng.random() < 0.02:
        base += rng.randint(5000, 30000)
    return min(base, 120000)


def pick_tenant(rng) -> int:
    return 1 + weighted(rng, [(i, w) for i, w in enumerate(TENANT_WEIGHTS)])


def next_ids(cur, table: str, n: int) -> list[int]:
    """显式分配连续 ID(基于当前 MAX(id)),保证 FK 可预知。"""
    cur.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}")
    base = cur.fetchone()[0]
    return list(range(base + 1, base + 1 + n))


def flush(cur, sql: str, rows: list[tuple], label: str) -> None:
    for i in range(0, len(rows), BATCH):
        cur.executemany(sql, rows[i:i + BATCH])
        conn_commit(cur)
    print(f"  [ok] {label}: {len(rows)} 行")


def conn_commit(cur):
    cur.connection.commit()


def main():
    p = argparse.ArgumentParser(description="百万级合成运营事件生成器")
    p.add_argument("--scale", type=int, default=1_000_000)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--user", default="hfusion")
    p.add_argument("--password", required=True)
    p.add_argument("--db", default="hfusionhub")
    p.add_argument("--truncate", action="store_true")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    rng = random.Random(args.seed)

    conn = pymysql.connect(host=args.host, port=args.port, user=args.user,
                           password=args.password, database=args.db,
                           charset="utf8mb4", autocommit=False)
    cur = conn.cursor()

    if args.truncate:
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        for table in ("agent_step", "agent_run", "agent_task",
                      "usage_event", "model_usage_record", "conversation"):
            cur.execute(f"TRUNCATE TABLE {table}")
            print(f"  [truncate] {table}")
        cur.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()

    start = dt.date.today()
    now = dt.datetime.now()
    n_calls = args.scale

    # ── 1) 合成用户与会话(FK 根) ────────────────────────────────────────────
    user_ids = next_ids(cur, "sys_user", N_USERS)
    user_rows = []
    for seq, uid in enumerate(user_ids):
        tenant_id = seq % 8 + 1
        user_rows.append((
            uid, f"seed_user_{uid}", f"$2a$10$seed-only-not-loginable-{uid:04d}",
            f"合成用户{uid}", "user", 0, tenant_id, now, now, 0))
    flush(cur, "INSERT INTO sys_user (id, username, password, nickname, role, "
               "status, tenant_id, created_at, updated_at, deleted) "
               "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", user_rows, "sys_user")

    conv_ids = next_ids(cur, "conversation", N_USERS * CONVS_PER_USER)
    conv_rows, conv_owner = [], {}
    k = 0
    for uidx, uid in enumerate(user_ids):
        tenant_id = uidx % 8 + 1
        for _ in range(CONVS_PER_USER):
            conv_rows.append((conv_ids[k], uid, tenant_id,
                              f"seed 会话 {conv_ids[k]}", now, now, 0))
            conv_owner[conv_ids[k]] = uid
            k += 1
    flush(cur, "INSERT INTO conversation (id, user_id, tenant_id, title, created_at, "
               "updated_at, deleted) VALUES (%s,%s,%s,%s,%s,%s,%s)",
          conv_rows, "conversation")

    user_tenant = {u[0]: u[6] for u in user_rows}

    # ── 2) Agent 链路(约 8% 事件量走 Agent) ────────────────────────────────
    n_agent = max(50, int(n_calls * 0.08))
    task_ids = next_ids(cur, "agent_task", n_agent)
    run_ids = next_ids(cur, "agent_run", n_agent)
    task_rows, run_rows, step_rows = [], [], []
    step_run_links = []   # (run_id, created_at) 供 step 生成
    for i in range(n_agent):
        tenant_id = pick_tenant(rng)
        uid = user_ids[i % N_USERS]
        cid = conv_ids[i % len(conv_ids)]
        created = synth_time(rng, start, args.days)
        status = weighted(rng, [("succeeded", 0.88), ("failed", 0.06),
                                ("timed_out", 0.03), ("cancelled", 0.03)])
        task_rows.append((
            task_ids[i], f"seed-task-{task_ids[i]:09d}", uid, tenant_id, cid,
            rng.randint(1, 6) if rng.random() < 0.5 else None,
            f"seed 合成任务 #{task_ids[i]}", status, None, created, created))
        run_status = "succeeded" if status == "succeeded" else weighted(
            rng, [("failed", 0.6), ("timed_out", 0.25), ("succeeded", 0.15)])
        err = None if run_status == "succeeded" else rng.choice(
            ["timeout", "connection_error", "tool_error"])
        tool = None if run_status == "succeeded" else f"tool_{rng.randint(1, 5)}"
        run_rows.append((
            run_ids[i], task_ids[i], f"seed-run-{run_ids[i]:09d}", 1, run_status,
            weighted(rng, MODELS), rng.randint(0, 8), err, tool,
            rng.randint(1000, 90000), created, created))
        for seq in range(1, rng.randint(3, 9)):
            step_type = weighted(rng, STEP_TYPES)
            step_err = rng.choice(STEP_ERROR_CODES)
            step_rows.append((
                run_ids[i], seq, step_type,
                step_type if step_type == "retrieval" else f"tool_{rng.randint(1, 5)}",
                rng.randint(20, 3000) if step_type != "model_generation"
                else latency_ms(rng),
                step_err, created + dt.timedelta(seconds=seq * rng.randint(2, 30))))
        step_run_links.append(run_ids[i])
    flush(cur, "INSERT INTO agent_task (id, request_id, user_id, tenant_id, "
               "conversation_id, knowledge_base_id, query, status, current_run_id, "
               "created_at, updated_at) "
               "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", task_rows, "agent_task")
    flush(cur, "INSERT INTO agent_run (id, task_id, run_uuid, attempt_number, status, "
               "model, tool_calls_count, error_code, failed_tool, duration_ms, "
               "created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
          run_rows, "agent_run")
    flush(cur, "INSERT INTO agent_step (run_id, sequence, step_type, action, "
               "duration_ms, error_code, created_at) "
               "VALUES (%s,%s,%s,%s,%s,%s,%s)", step_rows, "agent_step")

    # ── 3) model_usage_record(主事件流) ────────────────────────────────────
    mur_rows = []
    for idx in range(n_calls):
        model = weighted(rng, MODELS)
        tenant_id = pick_tenant(rng)
        req_type = weighted(rng, REQUEST_TYPES)
        prompt = lognormal_tokens(rng)
        completion = int(prompt * rng.uniform(0.2, 0.9))
        created = synth_time(rng, start, args.days)
        agent_task_id = task_ids[rng.randrange(n_agent)] if req_type == "agent" else None
        mur_rows.append((
            rng.randint(1, N_USERS), tenant_id,
            conv_ids[rng.randrange(len(conv_ids))] if rng.random() < 0.6 else None,
            agent_task_id, model, "deepseek" if "deepseek" in model else "ollama",
            prompt, completion, prompt + completion,
            round((prompt / 1e6) * 0.27 + (completion / 1e6) * 1.1, 6),
            latency_ms(rng), req_type, created))
    flush(cur, "INSERT INTO model_usage_record (user_id, tenant_id, conversation_id, "
               "agent_task_id, model, provider, prompt_tokens, completion_tokens, "
               "total_tokens, cost_usd, latency_ms, request_type, created_at) "
               "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", mur_rows,
          "model_usage_record")

    # ── 4) usage_event(RESERVE -> COMMIT/RELEASE 幂等链) ───────────────────
    event_rows = []
    for idx, row in enumerate(mur_rows):
        user_id, tenant_id, amount, req_type, created = row[0], row[1], row[8], row[11], row[12]
        meter = {"chat": "chat_tokens", "agent": "agent_tokens",
                 "embedding": "index_chunks", "evaluation": "chat_tokens"}[req_type]
        request_id = f"seed-mur-{user_ids[0] + idx:09d}"
        window_key = created.strftime("%Y-%m-%d")
        reserve = int(amount * rng.uniform(1.2, 1.8))
        event_rows.append((tenant_id, meter, "RESERVE", request_id, window_key,
                           reserve, "message", request_id, created))
        if rng.random() < 0.94:
            event_rows.append((tenant_id, meter, "COMMIT", request_id, window_key,
                               amount, "message", request_id,
                               created + dt.timedelta(seconds=rng.randint(1, 60))))
        else:
            event_rows.append((tenant_id, meter, "RELEASE", request_id, window_key,
                               reserve, "message", request_id,
                               created + dt.timedelta(seconds=rng.randint(1, 60))))
    flush(cur, "INSERT INTO usage_event (tenant_id, meter, operation, request_id, "
               "window_key, amount, ref_type, ref_id, created_at) "
               "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", event_rows, "usage_event")

    print(f"\n[done] 事件量级: mur={len(mur_rows)} usage_event={len(event_rows)} "
          f"agent链路 task/run/step={len(task_rows)}/{len(run_rows)}/{len(step_rows)}")
    print("[next] bash bigdata/scripts/full_import.py --dt <日期> 或等待 Flink CDC 增量")
    conn.close()


if __name__ == "__main__":
    main()
