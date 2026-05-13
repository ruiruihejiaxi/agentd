# 多 Agent 协作脚本 - 统一启动器
# 用法: python man.py
# 功能：自动启动 agentd.py，检测就绪后自动启动 ui.py

import subprocess
import sys
import os
import json
import time
import urllib.request
import urllib.error

STATUS_URL = "http://127.0.0.1:3001/api/status"
MAX_WAIT = 120  # 最大等待 agentd.py 就绪的时间（秒）
AGENTS_FILE = "agents.json"


def load_agents():
    """加载 agents.json"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), AGENTS_FILE)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    print("=" * 50)
    print("多 Agent 协作脚本启动器")
    print("=" * 50)
    print()

    # 加载 Agent 配置
    agents = load_agents()
    print(f"[man.py] 已加载 {len(agents)} 个 Agent 配置")
    print(f"[man.py] 请确保所有 Agent 进程已手动启动")
    print()

    # 输入会话名称（统一由 man.py 管理，agentd.py 不再弹窗询问）
    session_name = input("请输入会话名称（如 projectX，直接回车使用默认）: ").strip()
    if not session_name:
        session_name = f"session_{int(time.time())}"
        print(f"[man.py] 使用默认会话名: {session_name}")
    print()

    # 1. 启动 agentd.py（后台运行，不显示控制台窗口）
    print("[man.py] 正在启动 agentd.py（后台运行）...")
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NO_WINDOW  # 0x08000000
    agentd_proc = subprocess.Popen(
        [sys.executable, os.path.join(script_dir, "agentd.py"), "--session", session_name],
        cwd=script_dir,
        creationflags=creation_flags,
    )
    print(f"[man.py] agentd.py 已启动 (PID: {agentd_proc.pid})")
    print()

    # 2. 等待 agentd.py 就绪（HTTP 服务响应 /api/status）
    print(f"[man.py] 正在等待 agentd.py 就绪（最长等待 {MAX_WAIT} 秒）...")
    start_time = time.time()
    ready = False

    while time.time() - start_time < MAX_WAIT:
        try:
            req = urllib.request.Request(STATUS_URL)
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    print(f"[man.py] agentd.py 已就绪！（耗时 {int(time.time() - start_time)} 秒）")
                    ready = True
                    break
        except Exception:
            pass
        time.sleep(1)

    if not ready:
        print(f"[man.py] WARNING: agentd.py 未在 {MAX_WAIT} 秒内就绪，仍然启动 ui.py ...")

    # 3. 启动 ui.py（在新窗口中）
    print("[man.py] 正在启动 ui.py ...")
    ui_proc = subprocess.Popen(
        [sys.executable, os.path.join(script_dir, "ui.py")],
        cwd=script_dir,
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
    )
    print(f"[man.py] ui.py 已启动 (PID: {ui_proc.pid})")

    print()
    print("=" * 50)
    print("所有服务已启动!")
    print("=" * 50)
    print()
    print("提示：关闭此窗口不会关闭已启动的进程。")
    print("- agentd.py 在后台运行（无窗口），可查看 logs/agentd.log 了解状态")
    print("- 如需关闭所有服务，请关闭对应的控制台窗口或手动结束 agentd/UI 进程")

if __name__ == "__main__":
    main()
