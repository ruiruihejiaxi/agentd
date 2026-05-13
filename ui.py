# 多 Agent 协作脚本 - 用户输入窗口 (ui.py)
# 功能：Agent 卡片展示、状态呼吸灯、会话实时查看、输入发送、暂停功能

import os
import sys
import json
import time
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path
import urllib.request
import urllib.error

# ============== 配置 ==============
SCRIPT_DIR = Path(__file__).parent
SESSIONS_DIR = SCRIPT_DIR / "sessions"
STATUS_URL = "http://127.0.0.1:3001/api/status"
STATUS_UI_FILE = "_status_ui.json"  # UI 状态覆盖文件（解决与 agentd 的竞态写入）
POLL_INTERVAL = 1  # 状态刷新间隔（秒）
SESSION_REFRESH_INTERVAL = 2  # 会话面板刷新间隔（秒）

# ============== 全局变量 ==============
agents = []  # Agent 列表
agent_vars = {}  # Agent 勾选状态
agent_cards = {}  # Agent 卡片组件
checkbuttons = {}  # 勾选框
pause_buttons = {}  # 暂停按钮
breathing_labels = {}  # 呼吸灯画布
status_labels = {}  # 状态标签
depth_labels = {}  # 深层思考状态标签
last_reply_times = {}  # Agent -> last reply timestamp
animation_ids = {}  # 呼吸灯动画 ID
root = None
input_text = None
session_view = None  # 会话查看器
session_view_scrollbar = None
_previous_session_content = ""

# ============== 状态颜色 ==============
STATUS_COLORS = {
    "green": "#00FF00",   # 绿色 - 在线/空闲
    "yellow": "#FFFF00",  # 黄色 - 工作中
    "offline": "#888888", # 灰色 - 离线
    "red": "#FF0000",     # 红色 - 请求裁决
    "blue": "#00BFFF"     # 蓝色 - 等待确认
}

STATUS_EMOJI = {
    "green": "💚",
    "yellow": "💛",
    "offline": "🤍",
    "red": "❤️",
    "blue": "💙"
}

# ============== 工具函数 ==============

def load_agents():
    """加载 Agent 配置"""
    agents_file = SCRIPT_DIR / "agents.json"
    with open(agents_file, "r", encoding="utf-8") as f:
        return json.load(f)

def get_current_session():
    """获取当前会话目录"""
    if not SESSIONS_DIR.exists():
        return None
    
    sessions = [d for d in SESSIONS_DIR.iterdir() if d.is_dir()]
    if not sessions:
        return None
    
    latest = max(sessions, key=lambda d: d.stat().st_mtime)
    return latest

def get_session_file():
    """获取当前 session.md 文件路径"""
    session_dir = get_current_session()
    if not session_dir:
        return None
    return session_dir / "session.md"

def append_to_session(content):
    """追加内容到 session.md"""
    session_dir = get_current_session()
    if not session_dir:
        return False
    
    session_file = session_dir / "session.md"
    with open(session_file, "a", encoding="utf-8") as f:
        f.write(content + "\n")
    return True

def update_status_json(updates):
    """写入 UI 状态覆盖到 _status_ui.json（不再直接写 _status.json 避免竞态）

    每条覆盖记录带时间戳，60 秒后过期不再生效。
    """
    session_dir = get_current_session()
    if not session_dir:
        return False

    status_file = session_dir / STATUS_UI_FILE

    data = {"_updated_at": time.time()}
    data.update(updates)

    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    return True

def fetch_status():
    """获取状态：合并 agentd 的 _status.json 和 UI 的 _status_ui.json

    agentd 状态为主，UI 状态覆盖为辅（仅 60 秒内写入的生效）。
    避免两个进程直接读写同一文件导致的竞态。
    """
    status = {}

    # 1. 读取 agentd 状态（HTTP 优先，失败则读 _status.json 备份）
    try:
        req = urllib.request.Request(STATUS_URL)
        with urllib.request.urlopen(req, timeout=2) as resp:
            status = json.loads(resp.read().decode("utf-8"))
    except Exception:
        session_dir = get_current_session()
        if session_dir:
            status_file = session_dir / "_status.json"
            if status_file.exists():
                try:
                    with open(status_file, "r", encoding="utf-8") as f:
                        status = json.load(f)
                except Exception:
                    pass

    # 2. 合并 UI 状态覆盖（60 秒内写入的才生效）
    session_dir = get_current_session()
    if session_dir:
        ui_status_file = session_dir / STATUS_UI_FILE
        if ui_status_file.exists():
            try:
                with open(ui_status_file, "r", encoding="utf-8") as f:
                    ui_data = json.load(f)
                updated_at = ui_data.pop("_updated_at", 0)
                if time.time() - updated_at < 60:
                    for agent_name, agent_st in ui_data.items():
                        status[agent_name] = agent_st
            except Exception:
                pass

    return status

def send_pause(agent_name, endpoint):
    """发送暂停命令"""
    try:
        data = json.dumps({"command": "pause"}).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"暂停失败: {e}")
        return False

def animate_breathing(canvas, color, width=30, height=30):
    """呼吸灯动画（绿/黄平滑呼吸，红/蓝闪烁）"""
    name = None
    for n, c in breathing_labels.items():
        if c == canvas:
            name = n
            break

    if name and name in animation_ids and animation_ids[name]:
        try:
            canvas.after_cancel(animation_ids[name])
        except:
            pass

    is_blink = color in ("#FF0000", "#00BFFF")  # 红/蓝闪烁模式

    def step():
        if is_blink:
            # 闪烁模式：快速开关
            t = int(time.time() * 3) % 2  # 快速闪烁
            if t:
                canvas.delete("all")
                canvas.create_oval(2, 2, width-2, height-2, fill=color, outline="")
            else:
                canvas.delete("all")
                canvas.create_oval(2, 2, width-2, height-2, fill="#2b2b2b", outline="")
        else:
            # 呼吸模式：平滑变化
            t = (time.time() % 2) / 2
            intensity = abs(t - 0.5) * 2

            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)

            factor = 0.5 + 0.5 * intensity
            r = min(255, int(r * factor))
            g = min(255, int(g * factor))
            b = min(255, int(b * factor))

            hex_color = f"#{r:02x}{g:02x}{b:02x}"

            canvas.delete("all")
            canvas.create_oval(2, 2, width-2, height-2, fill=hex_color, outline="")

        if name:
            animation_ids[name] = canvas.after(50, step)

    step()

# ============== 深层思考状态检测 ==============

def check_agent_thinking_state():
    """检测 Agent 是否处于"思考中"状态（已通知但尚未回复）
    
    判断逻辑：
    - 若 session.md 最后一条是用户消息（#用户）且包含 @Agent 指向该 Agent
      且该 Agent 还没回复 → 思考中
    - 若 Agent 最近一小时的最后一条回复是黄色状态 → 思考中
    """
    session_file = get_session_file()
    if not session_file or not session_file.exists():
        return {}
    
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        thinking_agents = {}
        
        # 从后往前扫描，找到最后一条用户/Agent 发言
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            
            if line.startswith("## "):
                # Agent 的回复，标记它为"最近有回复"
                agent_name = line[3:].strip()
                for a in agents:
                    if a["name"] == agent_name:
                        thinking_agents[agent_name] = False  # 已回复
                break
            
            if line.startswith("#用户"):
                # 用户消息，扫描后续所有行找 ###
                for j in range(i + 1, len(lines)):
                    h3 = lines[j].strip()
                    if h3.startswith("### "):
                        targets_text = h3[4:]
                        tokens = targets_text.split()
                        for token in tokens:
                            target = token.lstrip("@").strip('"')
                            for a in agents:
                                if a["name"] == target and target not in thinking_agents:
                                    thinking_agents[target] = True  # 思考中
                        break
                break
        
        return thinking_agents
    except Exception:
        return {}

# ============== 会话实时查看 ==============

def refresh_session_view():
    """刷新会话查看面板（由 root.after 定时调用）"""
    global _previous_session_content, session_view
    
    if session_view is None:
        return
    
    session_file = get_session_file()
    if not session_file or not session_file.exists():
        root.after(int(SESSION_REFRESH_INTERVAL * 1000), refresh_session_view)
        return
    
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        if content != _previous_session_content:
            _previous_session_content = content
            
            # 更新文本
            session_view.config(state="normal")
            session_view.delete("1.0", "end")
            
            # 用颜色标注不同部分
            for line in content.split("\n"):
                if line.startswith("#用户"):
                    session_view.insert("end", line + "\n", "user_tag")
                elif line.startswith("## "):
                    session_view.insert("end", line + "\n", "agent_tag")
                elif line.startswith("### "):
                    session_view.insert("end", line + "\n", "h3_tag")
                elif line.startswith("**时间**") or line.startswith("**内容**") or line.startswith("**分歧**"):
                    session_view.insert("end", line + "\n", "field_tag")
                else:
                    session_view.insert("end", line + "\n", "normal")
            
            session_view.config(state="disabled")
            # 自动滚动到底部
            session_view.see("end")
    except Exception:
        pass
    
    root.after(int(SESSION_REFRESH_INTERVAL * 1000), refresh_session_view)

# ============== UI 组件 ==============

def create_agent_card(parent, agent, row, col):
    """创建 Agent 卡片"""
    name = agent["name"]
    
    frame = ttk.Frame(parent, padding=10, relief="raised", borderwidth=2)
    frame.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
    
    # Agent 名称
    name_label = ttk.Label(frame, text=name, font=("Arial", 12, "bold"))
    name_label.pack(pady=(0, 5))
    
    # 呼吸灯画布
    light_canvas = tk.Canvas(frame, width=30, height=30, bg="#2b2b2b", highlightthickness=0)
    light_canvas.pack(pady=5)
    
    # 状态标签
    status_label = ttk.Label(frame, text="离线", font=("Arial", 9))
    status_label.pack(pady=2)
    
    # 深层思考状态标签
    depth_label = ttk.Label(frame, text="", font=("Arial", 8, "italic"), foreground="#888")
    depth_label.pack(pady=(0, 2))
    
    # 勾选框
    var = tk.BooleanVar(value=False)
    cb = ttk.Checkbutton(frame, text=f"@\"{name}\"", variable=var)
    cb.pack(pady=5)
    
    # 暂停按钮
    pause_btn = ttk.Button(
        frame, 
        text="暂停",
        command=lambda: on_pause_click(name, agent["endpoint"])
    )
    pause_btn.pack(pady=5)
    
    # 保存组件引用
    agent_cards[name] = frame
    checkbuttons[name] = cb
    pause_buttons[name] = pause_btn
    breathing_labels[name] = light_canvas
    status_labels[name] = status_label
    depth_labels[name] = depth_label
    agent_vars[name] = var
    animation_ids[name] = None
    
    # 启动呼吸灯动画（初始为灰色）
    animate_breathing(light_canvas, STATUS_COLORS["offline"])

def on_pause_click(name, endpoint):
    """暂停按钮点击（异步发送 + 按钮状态反馈，防止 UI 卡死）"""
    btn = pause_buttons[name]
    btn.config(text="⏳ 暂停中...", state="disabled")

    def _do_pause():
        success = send_pause(name, endpoint)
        root.after(0, lambda: _update_pause_btn(name, success))

    threading.Thread(target=_do_pause, daemon=True).start()

def _update_pause_btn(name, success):
    """更新暂停按钮状态（2 秒后自动恢复）"""
    btn = pause_buttons[name]
    if success:
        btn.config(text="已暂停")
    else:
        btn.config(text="暂停失败")
    root.after(2000, lambda: btn.config(text="暂停", state="normal"))

def update_status_display():
    """更新状态显示（包含深层思考提示）"""
    status = fetch_status()
    thinking_state = check_agent_thinking_state()
    
    for agent in agents:
        name = agent["name"]
        agent_status = status.get(name, "offline")
        color = STATUS_COLORS.get(agent_status, STATUS_COLORS["offline"])
        emoji = STATUS_EMOJI.get(agent_status, STATUS_EMOJI["offline"])
        
        # 更新呼吸灯
        if name in breathing_labels:
            animate_breathing(breathing_labels[name], color)
        
        # 更新状态标签
        if name in status_labels:
            is_thinking = thinking_state.get(name, False)
            
            if is_thinking and agent_status == "yellow":
                status_text = "🧠 深度思考中..."
                status_labels[name].config(text=f"{status_text}")
                # 深层思考提示
                if name in depth_labels:
                    depth_labels[name].config(text=f"（正在调用 {name}...）", foreground="#FFA500")
            elif is_thinking and agent_status == "green":
                status_text = "🧠 思考中（空闲）"
                status_labels[name].config(text=f"{status_text}")
                if name in depth_labels:
                    depth_labels[name].config(text="（等待响应...）", foreground="#888")
            else:
                base_text = {
                    "green": "在线",
                    "yellow": "工作中",
                    "offline": "离线",
                    "red": "待裁决",
                    "blue": "等待确认"
                }.get(agent_status, "未知")
                status_labels[name].config(text=f"{emoji} {base_text}")
                if name in depth_labels:
                    depth_labels[name].config(text="", foreground="#888")

def update_loop():
    """状态更新循环"""
    while True:
        try:
            update_status_display()
        except Exception as e:
            print(f"状态更新异常: {e}")
        time.sleep(POLL_INTERVAL)

def on_send():
    """发送消息"""
    global input_text
    
    selected = []
    for name, var in agent_vars.items():
        if var.get():
            selected.append(name)
    
    if not selected:
        append_to_session("\n[系统提示：发送失败，请至少选择一个 Agent]")
        print("请至少选择一个 Agent")
        return

    content = input_text.get("1.0", "end-1c").strip()
    if not content:
        print("请输入内容")
        return

    # 检查 agentd 是否在线
    agentd_online = False
    try:
        req = urllib.request.Request(STATUS_URL)
        with urllib.request.urlopen(req, timeout=2):
            agentd_online = True
    except Exception:
        pass

    if not agentd_online:
        append_to_session("\n[系统提示：⚠️ 无法连接到调度器（agentd.py），消息已写入但 Agent 不会收到通知]")
        targets = " ".join([f"@\"{name}\"" for name in selected])
        message = f"\n#用户\n{content}\n### {targets}\n"
        if append_to_session(message):
            input_text.delete("1.0", "end")
        return

    # 检查会话文件
    session_file = get_session_file()
    if not session_file or not session_file.exists():
        print("发送失败：找不到会话文件")
        return

    targets = " ".join([f"@\"{name}\"" for name in selected])
    message = f"\n#用户\n{content}\n### {targets}\n"

    status_updates = {name: "yellow" for name in selected}
    update_status_json(status_updates)

    if append_to_session(message):
        print(f"消息已发送: 发送给 {', '.join(selected)}")
        input_text.delete("1.0", "end")
    else:
        append_to_session("\n[系统提示：发送失败，写入会话文件出错]")
        print("发送失败：写入会话文件出错")

def on_select_all():
    """全选"""
    for var in agent_vars.values():
        var.set(True)

def on_deselect_all():
    """取消全选"""
    for var in agent_vars.values():
        var.set(False)

def create_ui():
    """创建 UI"""
    global root, input_text, session_view
    
    root = tk.Tk()
    root.title("多 Agent 协作 - 用户窗口")
    root.geometry("950x750")
    root.minsize(600, 500)
    root.resizable(True, True)
    
    # 主题色
    bg_color = "#1e1e1e"
    fg_color = "#ffffff"
    input_bg = "#2d2d2d"
    root.configure(bg=bg_color)
    
    # ========== 主框架 ==========
    main_frame = ttk.Frame(root, padding=10)
    main_frame.pack(fill="both", expand=True)
    
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TFrame", background=bg_color)
    style.configure("TLabel", background=bg_color, foreground=fg_color)
    style.configure("TLabelframe", background=bg_color, foreground=fg_color)
    style.configure("TLabelframe.Label", background=bg_color, foreground=fg_color)
    style.configure("TButton", background="#444", foreground=fg_color)
    style.configure("TCheckbutton", background=bg_color, foreground=fg_color)
    
    # ========== 标题 ==========
    title_label = ttk.Label(main_frame, text="🤖 多 Agent 协作系统", font=("Arial", 14, "bold"))
    title_label.pack(pady=(0, 10))
    
    # ========== 主拖拽面板（垂直三区可调） ==========
    main_paned = tk.PanedWindow(main_frame, orient="vertical", sashwidth=8, sashrelief="raised", bg="#555")
    main_paned.pack(fill="both", expand=True, pady=(0, 5))

    # === Pane 1: Agent 卡片区（可拖拽调整高度，最小 120px） ===
    cards_container = ttk.Frame(main_paned)
    main_paned.add(cards_container, stretch="never", minsize=120)

    cards_frame = ttk.Frame(cards_container)
    cards_frame.pack(fill="x", pady=(5, 2))
    for i, agent in enumerate(agents):
        row = i // 4
        col = i % 4
        create_agent_card(cards_frame, agent, row, col)

    select_frame = ttk.Frame(cards_container)
    select_frame.pack(fill="x", pady=(0, 5))
    ttk.Button(select_frame, text="☑ 全选", command=on_select_all).pack(side="left", padx=2)
    ttk.Button(select_frame, text="☐ 取消全选", command=on_deselect_all).pack(side="left", padx=2)

    # === Pane 2: 会话查看器（可拖拽调整大小，主伸缩区，最小 100px） ===
    view_frame = tk.Frame(main_paned, bg="#1e1e1e")
    main_paned.add(view_frame, stretch="always", height=400, minsize=100)

    session_view = tk.Text(
        view_frame,
        font=("Consolas", 10),
        wrap="word",
        state="disabled",
        bg=input_bg,
        fg=fg_color,
        insertbackground=fg_color,
        relief="flat",
        borderwidth=5,
    )
    session_view.pack(side="left", fill="both", expand=True)

    scrollbar = tk.Scrollbar(view_frame, orient="vertical", command=session_view.yview, bg="#333")
    scrollbar.pack(side="right", fill="y")
    session_view.configure(yscrollcommand=scrollbar.set)

    # 语法高亮标签配置
    session_view.tag_configure("user_tag", foreground="#4FC3F7", font=("Consolas", 10, "bold"))
    session_view.tag_configure("agent_tag", foreground="#81C784", font=("Consolas", 10, "bold"))
    session_view.tag_configure("h3_tag", foreground="#FFB74D", font=("Consolas", 10))
    session_view.tag_configure("field_tag", foreground="#CE93D8", font=("Consolas", 10))
    session_view.tag_configure("normal", foreground=fg_color)

    # === Pane 3: 输入区域（可拖拽调整高度，最小 80px） ===
    input_container = tk.Frame(main_paned, bg="#1e1e1e")
    main_paned.add(input_container, stretch="never", height=150, minsize=80)

    input_label = ttk.Label(input_container, text="✏️ 输入消息（回车发送，Shift+回车换行）：", font=("Arial", 9))
    input_label.pack(anchor="w", pady=(2, 2))

    input_text = tk.Text(input_container, font=("Arial", 11), bg=input_bg, fg=fg_color, insertbackground=fg_color, relief="flat", borderwidth=3)
    input_text.pack(fill="both", expand=True, pady=(0, 3))
    input_text.bind("<Return>", lambda e: on_send() or "break")
    input_text.bind("<Shift-Return>", lambda e: input_text.insert("insert", "\n") or "break")
    
    # 发送按钮和状态栏在同一行
    bottom_frame = ttk.Frame(main_frame)
    bottom_frame.pack(fill="x", side="bottom")
    
    send_btn = ttk.Button(bottom_frame, text="🚀 发送", command=on_send, width=15)
    send_btn.pack(side="right", padx=(5, 0))
    
    status_bar = ttk.Label(bottom_frame, text="正在连接状态服务...", relief="sunken", anchor="w", background="#333", foreground="#aaa")
    status_bar.pack(fill="x", side="left", expand=True)
    
    # 启动状态更新线程
    threading.Thread(target=update_loop, daemon=True).start()
    
    # 启动会话视图刷新（使用 after 在主线程中）
    root.after(int(SESSION_REFRESH_INTERVAL * 1000), refresh_session_view)
    
    root.mainloop()

def main():
    global agents
    
    print("=" * 50)
    print("多 Agent 协作脚本 - ui")
    print("=" * 50)
    print()
    
    # 加载 Agent 配置
    agents = load_agents()
    print(f"已加载 {len(agents)} 个 Agent:")
    for agent in agents:
        print(f"  - {agent['name']}")
    
    # 检查会话是否存在
    session_dir = get_current_session()
    if not session_dir:
        print("等待 agentd.py 初始化...")
    else:
        print(f"当前会话: {session_dir.name}")
    
    print()
    print("启动 UI...")
    
    # 创建 UI
    create_ui()

if __name__ == "__main__":
    main()
