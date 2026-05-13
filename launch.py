#!/usr/bin/env python3
"""
agentd 一键启动工具 — 自动检测环境、启动服务、健康检查
Usage:
  python launch.py              # 完整启动所有服务
  python launch.py --status     # 查看运行状态
  python launch.py --stop       # 停止所有服务
"""
import os, sys, json, time, socket, subprocess, urllib.request, signal
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
BRIDGES_DIR = BASE_DIR / "bridges"
PROCESSES = []

def log(msg): print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}")

def port_used(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    r = s.connect_ex(("127.0.0.1", port))
    s.close()
    return r == 0

def launch(name, cmd, env_add=None):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if env_add: env.update(env_add)
    # 检查端口
    for i, arg in enumerate(cmd):
        if arg.isdigit() and i > 0 and ("PORT" in env_add or "port" in str(cmd[i-1]).lower()):
            if port_used(int(arg)):
                log(f"[{name}] 端口 {arg} 已被占用，跳过")
                return None
    try:
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
        PROCESSES.append(proc)
        log(f"[{name}] 启动成功 (PID: {proc.pid})")
        return proc
    except Exception as e:
        log(f"[{name}] 失败: {e}")
        return None

def stop_all():
    log("停止所有服务...")
    for proc in PROCESSES:
        try:
            if os.name == 'nt': subprocess.run(["taskkill", "-f", "-pid", str(proc.pid)], capture_output=True)
            else: proc.terminate()
        except: pass
    PROCESSES.clear()
    time.sleep(1)
    log("已全部停止")

def health_check():
    services = {
        "agentd 调度器": ("http://127.0.0.1:3001/api/status", "GET"),
        "WorkBuddy": ("http://127.0.0.1:3010/health", "GET"),
        "CodeBuddy": ("http://127.0.0.1:3011/health", "GET"),
        "WebUI": ("http://127.0.0.1:8080/", "GET"),
    }
    print(f"\n  ┌─ 服务状态 ─────────────────────────────┐")
    all_ok = True
    for name, (url, _) in services.items():
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = resp.read()[:100]
                print(f"  │ {name:20s}  ✔  在线")
        except:
            print(f"  │ {name:20s}  ✘  离线")
            all_ok = False
    print(f"  └────────────────────────────────────────┘")
    return all_ok

def do_start():
    print(f"\n  ╔══════════════════════════════════════════╗")
    print(f"  ║     agentd 系统启动                       ║")
    print(f"  ╚══════════════════════════════════════════╝\n")

    # 1. 检查环境
    log("检查环境...")
    # 2. 启动 CodeBuddy bridge (端口 3011)
    launch("CodeBuddy", [sys.executable, str(BRIDGES_DIR / "universal_bridge.py")], {
        "BRIDGE_NAME": "CodeBuddy",
        "BRIDGE_PORT": "3011",
        "LLM_API_KEY": "",  # set LLM_API_KEY env var before running
        "LLM_API_URL": "https://api.deepseek.com/v1/chat/completions",
        "LLM_MODEL": "deepseek-chat",
    })
    time.sleep(2)

    # 3. 启动 WorkBuddy bridge (端口 3010)
    launch("WorkBuddy", [sys.executable, str(BRIDGES_DIR / "workbuddy" / "workbuddy_bridge.py")], {
        "LLM_API_KEY": "",  # set LLM_API_KEY env var before running
    })
    time.sleep(2)

    # 4. 启动 agentd 调度器 (端口 3001)
    launch("AgentD", [sys.executable, str(BASE_DIR / "agentd.py"), "--session", "default"])
    time.sleep(2)

    # 5. 启动 Web UI (端口 8080)
    launch("WebUI", [sys.executable, str(BASE_DIR / "webui.py")])
    time.sleep(2)

    # 6. 健康检查
    health_check()
    print(f"\n  ┌─ 访问入口 ──────────────────────────────┐")
    print(f"  │ WebUI:     http://localhost:8080         │")
    print(f"  │ 状态API:   http://localhost:3001/api/status│")
    print(f"  │ WorkBuddy: http://localhost:3010/health  │")
    print(f"  │ CodeBuddy: http://localhost:3011/health  │")
    print(f"  └────────────────────────────────────────┘")
    print(f"\n  python launch.py --stop  # 停止所有服务")

def do_status():
    agents_file = BASE_DIR / "agents.json"
    if agents_file.exists():
        agents = json.loads(agents_file.read_text("utf-8"))
        print(f"\n  Agent 配置 ({len(agents)} 个):")
        for a in agents:
            ep = a["endpoint"]
            port = ep.split(":")[-1].split("/")[0]
            status = "端口开放" if port_used(int(port)) else "端口关闭"
            print(f"    {a['name']:15s} {status:12s} {ep}")
    else:
        print("\n  agents.json 未找到")
    health_check()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="agentd 启动器")
    parser.add_argument("action", nargs="?", default="start", choices=["start", "stop", "status"])
    args = parser.parse_args()
    if args.action == "start": do_start()
    elif args.action == "stop": stop_all()
    elif args.action == "status": do_status()

if __name__ == "__main__":
    main()
