#!/usr/bin/env bash
# check_p4.sh — P4 推进器验收(issue #5)。写入仅限测试 Base(Base 守卫兜底)。
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export ALERT_DRY_RUN=1
FAIL=0
pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; FAIL=1; }

echo "① 纯函数单测(runbook+guard)"
if python3 -m unittest discover -s tests 2>&1 | grep -q "^OK"; then pass "unittest OK"; else fail "unittest 失败"; fi

echo "② 模拟一天(播种→引擎→断言→清场)"
if GY_PER_RUN_COPY_LIMIT=10 python3 scripts/sim_day.py >/tmp/gy_sim.log 2>&1; then
  pass "sim_day 通过($(grep -c '✓' /tmp/gy_sim.log) 项断言)"
else
  fail "sim_day 失败(见 /tmp/gy_sim.log)"; tail -5 /tmp/gy_sim.log | sed 's/^/    /'
fi

echo "③ 告警链:引擎异常→即时告警"
OUT=$(python3 - <<'PY' 2>&1
import sys
sys.path.insert(0, ".")
from unittest import mock
from orchestrator import engine, feishu_io
with mock.patch.object(feishu_io, "list_records", side_effect=RuntimeError("模拟崩溃")):
    try:
        engine.run(mode="heartbeat")
    except RuntimeError:
        print("ALARM-TEST-RAISED")
PY
)
if echo "$OUT" | grep -q "alert:dry" && echo "$OUT" | grep -q "推进器异常" && echo "$OUT" | grep -q "ALARM-TEST-RAISED"; then
  pass "异常→告警→重抛 全链通"
else
  fail "告警链断:$OUT"
fi

echo "④ daily 轮 + 月度成本核算"
# 验收只测日报/成本，不应把真实 planner 结果物化进运营 Base。
OUT=$(python3 -m orchestrator.run --mode daily --skip-plan 2>&1)
if echo "$OUT" | grep -q "monthly_cost_cny" && echo "$OUT" | grep -q "本月累计 LLM 成本"; then
  pass "daily 日报含月成本($(echo "$OUT" | grep -o '本月累计 LLM 成本 ¥[0-9.]*' | head -1))"
else
  fail "daily 轮无月成本输出"
fi

echo "⑤ 备份产出 5 表"
if python3 scripts/backup_tables.py >/tmp/gy_bak.log 2>&1; then
  N=$(ls backups/test-$(date +%Y%m%d)/*.json 2>/dev/null | wc -l | tr -d ' ')
  [ "$N" -ge 5 ] && pass "backups/ 下 $N 表" || fail "备份文件 $N (<5)"
else
  fail "backup_tables.py 失败"
fi

echo "⑥ flock 单实例互斥"
python3 - <<'PY' &
import fcntl, time, pathlib
lf = open(pathlib.Path("locks/orchestrator.lock"), "w")
fcntl.flock(lf, fcntl.LOCK_EX)
time.sleep(4)
PY
HOLDER=$!
sleep 1
OUT=$(python3 -m orchestrator.run --mode heartbeat 2>&1)
wait $HOLDER
if echo "$OUT" | grep -q "另一实例运行中"; then pass "并发第二实例被锁拒"; else fail "锁互斥失效"; fi

echo "⑦ cron 安装脚本(仅预览,不装)"
if bash scripts/install_cron.sh | grep -c "orchestrator.run\|backup_tables" | grep -q "3"; then
  pass "install_cron 预览 3 条目;开发期不安装"
else
  fail "install_cron 预览异常"
fi

echo
[ "$FAIL" -eq 0 ] && echo "✅ P4 验收全部通过" || echo "❌ P4 验收有失败项"
exit "$FAIL"
