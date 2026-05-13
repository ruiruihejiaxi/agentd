#!/usr/bin/env python3
"""
agentd 生存监控 v1.0
跟踪 API 余额消耗，记录每天烧了多少
"""
import json
import os
import time
import urllib.request
from datetime import datetime
from pathlib import Path

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY", "")
LOG_FILE = str(Path(__file__).parent.parent / "logs" / "survival.json")

def get_balance():
    req = urllib.request.Request(
        "https://api.deepseek.com/user/balance",
        headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            for info in data.get("balance_infos", []):
                if info.get("currency") == "CNY":
                    return float(info["total_balance"])
    except Exception as e:
        print(f"[监控] 查询余额失败: {e}")
    return None


def log_check():
    balance = get_balance()
    if balance is None:
        return

    now = datetime.now().isoformat()
    records = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            try:
                records = json.load(f)
            except:
                records = []

    # 计算消耗
    prev = records[-1].get("balance", balance) if records else balance
    consumed = round(prev - balance, 3) if prev > balance and isinstance(prev, (int, float)) else 0

    records.append({
        "time": now,
        "balance": balance,
        "consumed_since_last": consumed if consumed > 0 else 0
    })

    # 只保留最近100条
    if len(records) > 100:
        records = records[-100:]

    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    # 当日统计
    today = now[:10]
    today_records = [r for r in records if r.get("time","").startswith(today)]
    today_consumed = sum(r.get("consumed_since_last", 0) for r in today_records)

    print(f"[{now[:19]}] 余额: {balance:.3f} CNY | 今日消耗: ~{today_consumed:.3f} CNY")


def show_history():
    if not os.path.exists(LOG_FILE):
        print("暂无记录")
        return
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        records = json.load(f)

    if not records:
        print("暂无记录")
        return

    print(f"\n=== 余额历史 (共 {len(records)} 条记录) ===")
    for r in records[-10:]:
        c = f"(-{r['consumed_since_last']:.3f})" if r.get('consumed_since_last', 0) > 0 else ""
        print(f"  {r.get('time','?')[:19]}  {r.get('balance',0):.3f} CNY {c}")

    first_balance = records[0].get("balance", 0)
    last_balance = records[-1].get("balance", 0)
    total = round(first_balance - last_balance, 3)
    print(f"\n总计消耗: {total:.3f} CNY (从 {first_balance:.3f} → {last_balance:.3f})")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--history":
        show_history()
    else:
        log_check()
