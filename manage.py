#!/usr/bin/env python3
"""
agentd 管理 CLI - 启动/停止/监控/余额一站式管理
"""
import os
import sys
import json
import time
import signal
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

BASE_DIR = r"D:\agentd"
PROCESSES = []

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def check_port(port):
    """检查端口是否可用"""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(("127.0.0.1", port))
    sock.close()
    return result != 0  # True = 端口空闲

def start_bridge(name, port, extra_env=None):
    """启动一个 Agent bridge"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if extra_env:
        env.update(extra_env)

    if name == "WorkBuddy":
        script = os.path.join(BASE_DIR, "bridges", "workbuddy", "workbuddy_bridge.py")
        env["LLM_API_KEY"] = env.get("LLM_API_KEY", "")
    elif name == "CodeBuddy":
        script = os.path.join(BASE_DIR, "bridges", "universal_bridge.py")
        env["BRIDGE_NAME"] = "CodeBuddy"
        env["BRIDGE_PORT"] = "3011"
        env["LLM_API_KEY"] = env.get("LLM_API_KEY", "")
        env["LLM_API_URL"] = "https://api.deepseek.com/v1/chat/completions"
        env["LLM_MODEL"] = "deepseek-chat"
    else:
        log(f"未知 Agent: {name}")
        return None

    if not check_port(port):
        log(f"[{name}] 端口 {port} 已被占用，跳过")
        return None

    proc = subprocess.Popen(
        [sys.executable, script],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    )
    PROCESSES.append(proc)
    log(f"[{name}] 已启动 (PID: {proc.pid}, 端口: {port})")
    return proc

def start_scheduler():
    """启动 agentd 调度器"""
    if not check_port(3001):
        log("[agentd] 端口 3001 已被占用，跳过")
        return None

    script = os.path.join(BASE_DIR, "agentd.py")
    proc = subprocess.Popen(
        [sys.executable, script, "--session", "default"],
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    )
    PROCESSES.append(proc)
    log(f"[agentd] 调度器已启动 (PID: {proc.pid})")
    return proc

def start_ui():
    """启动 UI"""
    script = os.path.join(BASE_DIR, "ui.py")
    proc = subprocess.Popen(
        [sys.executable, script],
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    )
    PROCESSES.append(proc)
    log(f"[UI] 用户界面已启动 (PID: {proc.pid})")
    return proc

def stop_all():
    """停止所有进程"""
    log("正在停止所有进程...")
    for proc in PROCESSES:
        try:
            if os.name == 'nt':
                subprocess.run(["taskkill", "-f", "-pid", str(proc.pid)], capture_output=True)
            else:
                proc.terminate()
        except:
            pass
    PROCESSES.clear()
    log("所有进程已停止")

def check_health():
    """检查各服务健康状态"""
    services = {
        "agentd": ("http://127.0.0.1:3001/api/status", "调度器"),
        "WorkBuddy": ("http://127.0.0.1:3010/health", "Agent"),
        "CodeBuddy": ("http://127.0.0.1:3011/health", "Agent"),
    }

    print(f"\n=== 服务状态 ({datetime.now().strftime('%H:%M:%S')}) ===")
    for name, (url, stype) in services.items():
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                if stype == "调度器":
                    agents = data.get("agents", {})
                    agent_status = " | ".join([f"{k}:{v}" for k, v in agents.items()])
                    print(f"  [OK] {name} ({stype}) - {agent_status}")
                else:
                    print(f"  [OK] {name} ({stype}) - {data.get('model','unknown')}")
        except Exception as e:
            print(f"  [OFF] {name} ({stype}) - {str(e)[:40]}")

def check_balance():
    """检查 DeepSeek 余额"""
    try:
        subprocess.run(
            [sys.executable, os.path.join(BASE_DIR, "scripts", "survival.py")],
            cwd=BASE_DIR
        )
    except:
        print("余额查询失败")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="agentd 管理 CLI")
    parser.add_argument("action", nargs="?", default="status",
                        choices=["start", "stop", "restart", "status", "balance", "monitor", "webui"],
                        help="操作")
    args = parser.parse_args()

    if args.action == "start":
        print("=" * 50)
        print("  agentd 系统启动")
        print("=" * 50)
        start_bridge("WorkBuddy", 3010)
        start_bridge("CodeBuddy", 3011)
        time.sleep(2)
        start_scheduler()
        time.sleep(2)
        start_ui()
        check_health()

    elif args.action == "stop":
        stop_all()

    elif args.action == "restart":
        stop_all()
        time.sleep(2)
        start_bridge("WorkBuddy", 3010)
        start_bridge("CodeBuddy", 3011)
        time.sleep(2)
        start_scheduler()
        time.sleep(2)
        start_ui()
        check_health()

    elif args.action == "status":
        check_health()

    elif args.action == "balance":
        check_balance()

    elif args.action == "monitor":
        print("监控模式 (每30秒刷新, Ctrl+C退出)")
        try:
            while True:
                check_health()
                time.sleep(30)
        except KeyboardInterrupt:
            print("\n监控已停止")

    elif args.action == "webui":
        print("启动 Web 控制台...")
        script = os.path.join(BASE_DIR, "webui.py")
        proc = subprocess.Popen(
            [sys.executable, script],
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        PROCESSES.append(proc)
        print(f"[WebUI] 已启动: http://localhost:8080 (PID: {proc.pid})")

if __name__ == "__main__":
    main()
