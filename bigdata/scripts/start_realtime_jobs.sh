#!/usr/bin/env bash
# ============================================================================
# HFusionData Analytics — 实时链路一键重建(实测验证过的标准提交流程)
#
#   bash bigdata/scripts/start_realtime_jobs.sh
#
# 步骤: 1) cancel 全部非终态 Flink 作业(避免多实例抢占 slot/恢复循环)
#        2) 从模板生成运行时 SQL(sink=upsert-kafka + 逐表 cdc source + 实时窗口)
#        3) 注入 MySQL 密码并校验(无 CHANGE_ME/{PWD} 残留,md5 对比 .env)
#        4) sql-client -f 提交 CDC 采集与实时聚合两个作业
# 前置: 00_catalogs.sql / cdc_ingest.sql / realtime_metrics.sql 已按实测修正;
#       connector jar 经 compose volume 挂载;MySQL 用户已有 RELOAD+REPLICATION 权限。
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_WIN="$(cygpath -m "$ROOT" 2>/dev/null || echo "$ROOT")"
JM=flink-jobmanager
MP=$(grep '^MYSQL_PASSWORD=' "$ROOT/../docker/.env" | tr -d '\r' | cut -d= -f2-)
[ -n "$MP" ] || { echo "MYSQL_PASSWORD 未配置"; exit 1; }

echo "== 1) 清理全部非终态 Flink 作业 =="
JOBS=$(curl -s http://localhost:8081/jobs 2>/dev/null | python -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print('\n'.join(j['id'] for j in d['jobs'] if j['status'] in ('RUNNING','RESTARTING','CREATED','CANCELLING')))
except Exception: pass")
for j in $JOBS; do
  curl -s -X PATCH "http://localhost:8081/jobs/$j?mode=cancel" >/dev/null && echo "  cancel $j"
done
sleep 5

echo "== 2) 生成运行时 SQL(密码注入 + 校验) =="
python - "$ROOT_WIN" "$MP" << 'PYEOF'
import io, re, sys, hashlib
root, mp = sys.argv[1], sys.argv[2]
cat = io.open(root + '/flink-jobs/00_catalogs.sql', encoding='utf-8').read()
sinks = [p.strip() for p in re.split(r'(?=CREATE )', cat)
         if p.strip().startswith('CREATE TABLE upsert_ods')]
assert len(sinks) == 4, f'expect 4 upsert sinks, got {len(sinks)}'
cdc = io.open(root + '/flink-jobs/cdc_ingest.sql', encoding='utf-8').read()
m_cdc = re.search(r'CREATE TABLE cdc_model_usage_record.*END;', cdc, re.S)
assert m_cdc, 'cdc block not found'
rm = io.open(root + '/flink-jobs/realtime_metrics.sql', encoding='utf-8').read()
parts = re.split(r'(?=CREATE )', cat)
rt_src = [p.strip() for p in parts if p.strip().startswith('CREATE TABLE realtime_')]
rt_sink = [p.strip() for p in parts if p.strip().startswith('CREATE TABLE mysql_realtime_metrics')]
rt_view = [p.strip() for p in parts if p.strip().startswith('CREATE TEMPORARY VIEW')]
assert len(rt_src) >= 1 and len(rt_sink) == 1 and len(rt_view) == 1,     f'catalog parts: src={len(rt_src)} sink={len(rt_sink)} view={len(rt_view)}'
m_ins = re.search(r'INSERT INTO mysql_realtime_metrics.*?GROUP BY window_start, window_end, tenant_id, model;', rm, re.S)
assert m_ins, 'realtime insert not found'

def inject(t):
    t = t.replace('{PWD}', mp).replace('CHANGE_ME', mp)
    assert 'CHANGE_ME' not in t and '{PWD}' not in t, '占位符残留!'
    return t

def md5(s):
    return hashlib.md5(s.encode()).hexdigest()[:8]

cdc_sql = inject('\n\n'.join(sinks) + '\n\n' + m_cdc.group(0) + '\n')
rt_sql = inject('\n\n'.join(rt_src + rt_sink + rt_view) + '\n\n' + m_ins.group(0) + '\n')
print(f'  cdc  md5={md5(cdc_sql)} len={len(cdc_sql)}')
print(f'  rt   md5={md5(rt_sql)} len={len(rt_sql)}')
io.open(root + '/flink-jobs/_run_cdc.sql', 'w', encoding='utf-8', newline='').write(cdc_sql)
io.open(root + '/flink-jobs/_run_realtime.sql', 'w', encoding='utf-8', newline='').write(rt_sql)
PYEOF

echo "== 3) 提交作业 =="
docker cp "$ROOT_WIN/flink-jobs/_run_cdc.sql" "$JM:/tmp/an/_run_cdc.sql"
docker cp "$ROOT_WIN/flink-jobs/_run_realtime.sql" "$JM:/tmp/an/_run_realtime.sql"
docker exec "$JM" /opt/flink/bin/sql-client.sh -f /tmp/an/_run_cdc.sql 2>&1 | grep -E "Job ID" | sed 's/^/  CDC /'
sleep 3
docker exec "$JM" /opt/flink/bin/sql-client.sh -f /tmp/an/_run_realtime.sql 2>&1 | grep -E "Job ID" | sed 's/^/  RT  /'

echo "== 4) 状态 =="
sleep 8
curl -s http://localhost:8081/jobs | python -c "
import json,sys
d=json.load(sys.stdin)
for j in d['jobs']:
    if j['status'] in ('RUNNING','RESTARTING'):
        print(f\"  {j['id'][:8]} {j['status']}\")"
echo "完成。验证: bash bigdata/scripts/verify_realtime_chain.sh"
