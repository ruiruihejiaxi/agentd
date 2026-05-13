#!/usr/bin/env python3
"""
agentd 全自动演示脚本
启动所有服务 → 创建演示会话 → 展示协作流程
"""
import os
import sys
import json
import time
import subprocess
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DEMO_SESSION = "demo"
SESSIONS_DIR = BASE_DIR / "sessions" / DEMO_SESSION
PROCESSES = []

def log(msg):
    t = datetime.now().strftime("%H:%M:%S")
    print(f"  [{t}] {msg}")

def check_port(port):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    r = s.connect_ex(("127.0.0.1", port))
    s.close()
    return r != 0

def start_process(name, cmd, env_add=None):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if env_add:
        env.update(env_add)
    try:
        proc = subprocess.Popen(
            cmd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        PROCESSES.append(proc)
        log(f"[{name}] 已启动 (PID: {proc.pid})")
        return proc
    except Exception as e:
        log(f"[{name}] 启动失败: {e}")
        return None

def stop_all():
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
    time.sleep(1)

def demo_full():
    """完整演示：启动 → 创建会话 → 展示状态"""
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║        agentd 全自动演示                  ║")
    print("  ╚══════════════════════════════════════════╝")
    print()

    # Step 1: Check prerequisites
    log("检查环境...")
    agents_file = BASE_DIR / "agents.json"
    if not agents_file.exists():
        log("错误: agents.json 不存在")
        return False
    with open(agents_file) as f:
        agents = json.load(f)
    log(f"已加载 {len(agents)} 个 Agent 配置")
    for a in agents:
        log(f"  - {a['name']}: {a['role']} ({a['endpoint']})")

    # Step 2: Check which ports are available
    for agent in agents:
        endpoint = agent["endpoint"]
        port = int(endpoint.split(":")[-1].split("/")[0])
        status = "可用" if check_port(port) else "已被占用"
        log(f"  端口 {port} ({agent['name']}): {status}")

    port_3001 = check_port(3001)
    log(f"  端口 3001 (agentd): {'可用' if port_3001 else '已被占用'}")

    # Step 3: Create demo session structure
    log(f"创建演示会话: {DEMO_SESSION}")
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    session_file = SESSIONS_DIR / "session.md"
    session_content = """# 协作文件

## 规则摘要
- 用户通过脚本窗口输入，脚本自动格式化为 #用户 开头并追加
- Agent 用 ## 开头回复，严格按规则格式
- 所有人只追加，不修改已有内容

---

## 演示会话

#用户
启动 agentd 演示系统，展示多 Agent 协作能力。
请两位 Agent 自我介绍并展示你们的专长领域。
### @WorkBuddy @CodeBuddy

"""
    with open(session_file, "w", encoding="utf-8") as f:
        f.write(session_content)
    log(f"会话文件已创建: {session_file}")

    # Step 4: Create status file
    status_data = {agent["name"]: "offline" for agent in agents}
    with open(SESSIONS_DIR / "_status.json", "w") as f:
        json.dump(status_data, f)
    log("状态文件已创建")

    # Step 5: Show WebUI info
    log(f"Web 控制台: http://localhost:8080")
    log(f"状态 API: http://localhost:3001/api/status")

    # Step 6: Print instructions
    print()
    print("  ═══════════════════════════════════════")
    print("   演示准备完成")
    print()
    print("   启动完整系统:")
    print("     python manage.py start")
    print()
    print("   或分步启动:")
    print("     1. python bridges/universal_bridge.py  (CodeBuddy)")
    print("     2. python agentd.py --session demo     (调度器)")
    print("     3. python webui.py                     (WebUI)")
    print()
    print("   浏览器打开: http://localhost:8080")
    print("  ═══════════════════════════════════════")
    print()

    return True

def demo_webui_only():
    """快速展示 WebUI"""
    log("启动 Web 控制台 (独立模式)...")
    webui_script = BASE_DIR / "webui.py"
    proc = start_process("WebUI", [sys.executable, str(webui_script)])
    if proc:
        time.sleep(2)
        try:
            req = urllib.request.Request("http://127.0.0.1:8080/")
            with urllib.request.urlopen(req, timeout=3) as resp:
                log(f"WebUI 响应: HTTP {resp.status} ({len(resp.read())} bytes)")
        except Exception as e:
            log(f"WebUI 未响应: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="agentd 自动演示")
    parser.add_argument("mode", nargs="?", default="full", choices=["full", "webui", "clean"])
    args = parser.parse_args()

    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║        agentd 演示系统                    ║")
    print("  ╚══════════════════════════════════════════╝")

    if args.mode == "full":
        demo_full()
    elif args.mode == "webui":
        demo_webui_only()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            stop_all()
    elif args.mode == "clean":
        stop_all()
        log("清理完成")
