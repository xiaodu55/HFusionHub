#!/usr/bin/env bash
# 数 pytest 汇总行里的 skipped 条数：只要有任何 skip 就判红。
# 容器专项的 skip 意味着 P0 门禁其实没执行（缺 Docker 守护进程、缺基础镜像等），
# "跑过了但跳过了" 不能算绿。
#
# 为什么是独立脚本而不是 workflow 里的一行 grep：在 `set -euo pipefail` 下
# `echo "$output" | grep -oE '[0-9]+ skipped'` 在**零命中**时返回 1，pipefail 让这个
# 赋值失败，set -e 直接把步骤打死 —— 也就是"套件一条 skip 都没有"这个理想形态必然红。
# 实测 bash 5.2.37：输入 `42 passed in 23.65s` 退出 1，输入 `33 passed, 6 skipped in 12.0s`
# 才走到判断。语义正好是反的。
#
# 退出码契约（由 python-ai/tests/test_ci_workflow_gates.py 直接执行本脚本钉住）：
#   0 = 有汇总行且 0 skipped
#   1 = 有 skipped（把条数打到 stdout）
#   2 = 读不到汇总行（采集阶段就崩等），绝不当成"0 skipped" 放过去
#
# 输入：pytest 的完整输出走 stdin。只统计**汇总行**，因为 `-rs` 的逐条原因行里
# 也含 "1 skipped" 字样，按行全查会重复计数。
set -u

output=$(cat)

summary=$(printf '%s\n' "$output" | grep -E \
  '[0-9]+ (passed|failed|errors?|skipped|warnings|xfailed|xpassed|deselected).* in [0-9.]+s' \
  | tail -n 1 || true)

if [ -z "$summary" ]; then
  echo "check_container_skips: no pytest summary line - cannot read the result." >&2
  exit 2
fi

skipped=0
for count in $(printf '%s\n' "$summary" | grep -oE '[0-9]+ skipped' | grep -oE '[0-9]+' || true); do
  skipped=$((skipped + count))
done

if [ "$skipped" -gt 0 ]; then
  echo "container suite has ${skipped} skipped test(s) - the gate did not actually run: ${summary}"
  exit 1
fi

echo "container suite ran with 0 skipped tests: ${summary}"
exit 0
