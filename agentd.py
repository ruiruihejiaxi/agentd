# 多 Agent 协作脚本 - 主调度程序 (agentd.py)
# 负责：文件监控、解析格式、通知 Agent、状态同步

import os
import sys
import json
import time
import socket
import traceback
import http.server
import socketserver
import threading
import urllib.request
import urllib.error
from pathlib import Path

# ============== 配置 ==============
SCRIPT_DIR = Path(__file__).parent
SESSIONS_DIR = SCRIPT_DIR / "sessions"
LOG_DIR = SCRIPT_DIR / "logs"
AGENTS_FILE = SCRIPT_DIR / "agents.json"
STATUS_PORT = 3001

# 轮询间隔（秒）
POLL_INTERVAL = 2
SIGNUP_TIMEOUT = 60  # 签到超时（秒）

# ============== 全局状态 ==============
current_session = None  # 当前会话名
session_dir = None  # 当前会话目录
file_pos = 0  # 已读文件位置
status_data = {}  # Agent 状态
agent_status_lock = threading.Lock()

# Agent 工作状态追踪（用于状态判断）
agent_last_activity = {}  # name -> timestamp，最后活动时间
last_reply_author = None  # 最后回复的 Agent 名称（防循环用）
task_completed = False  # ### 任务完成 标记，用于停止 Agent 间通知流转
consecutive_agent_rounds = 0  # 连续 Agent 间对话轮数，超过上限自动暂停防循环
MAX_CONSECUTIVE_ROUNDS = 10  # 最大连续 Agent 对话轮数
WORKING_TIMEOUT = 120  # 120秒无活动才变回绿色（从"工作中"状态）

# ============== 模板文件 ==============

SESSION_TEMPLATE = """# 协作文件

## 规则摘要
- 用户通过脚本窗口输入，脚本自动格式化为 #用户 开头并追加
- Agent 用 ## 开头回复，严格按 RULES.md 的格式
- 所有人只追加，不修改已有内容
- 三级标题 ### 指示下一步谁行动
- 技术栈规范见 TECH_STACK.md，后续开发必须遵守

---

（以下是正式协作内容，从上往下阅读）
"""

TECH_STACK_TEMPLATE = """# 技术栈规范

> 本文件记录项目讨论确定的技术栈和技术规范，所有后续开发必须严格遵守。
> 如需修改规范，必须在协作中提出并获得双方确认后更新。

## 版本信息
- **创建时间**：[由 Agent 填写]
- **最后更新**：[由 Agent 填写]
- **参与 Agent**：[由 Agent 填写]

---

## 技术选型

### 语言与框架
| 类别 | 选择 | 版本/备注 |
|------|------|----------|
| 前端框架 | - | - |
| 后端框架 | - | - |
| 语言 | - | - |

### 数据库
| 用途 | 类型 | 连接信息 |
|------|------|----------|
| 主数据库 | - | - |

### 工具链
| 工具 | 用途 | 配置 |
|------|------|------|
| - | - | - |

---

## 代码规范

### 目录结构
```
project/
```

### 命名规范
- 文件命名：
- 变量命名：
- API 命名：

### 代码风格
-

---

## 接口规范

### REST API
| 端点 | 方法 | 说明 |
|------|------|------|
| - | - | - |

### WebSocket
| 事件 | 方向 | 说明 |
|------|------|------|
| - | - | - |

---

## 部署规范
-

---

## 其他约定
-
"""

RULES_TEMPLATE = """# 协作规则（参考，可按项目需要修改）

## 文件用途
本文件是 Agent 与 Agent、Agent 与用户之间的交互面板。
- 只写入结论、方案、沟通内容、下一步计划
- 不写入大段代码、操作日志、调试输出
- 你的内部推理过程不写入，只写对外展示的结论
- 内容精简，确保对方和用户能看懂进展到哪一步
- 如需展示详细内容，写入 worklogs/ 下你的工作日志文件，
  在共享文件中只贴路径和摘要，告知对方去对应路径查看

## 发言格式
**重要**：Agent 名称可能包含空格（如 "Claude Code"），请使用双引号包裹：
- `@"Claude Code"` 表示通知名为 "Claude Code" 的 Agent
- 收到通知时，脚本会正确解析双引号包裹的名称

## 技术栈规范（TECH_STACK.md）
讨论确定技术栈后，**必须将结论写入 TECH_STACK.md**，固化规范。
- 技术栈包括但不限于：语言、框架、数据库、工具链、代码规范
- 后续所有开发必须严格遵守 TECH_STACK.md 中的规范
- 如需修改规范，必须在协作中提出并获得双方确认后更新

## 并发写入约定
为避免多 Agent 同时写入导致内容穿插，请遵守以下约定：
1. 写入前先读取文件末尾，检查最后一条发言的 Agent
2. 如果是另一个 Agent 最近（10秒内）有发言，等待 1-2 秒再写入
3. 写入时只追加，不修改已有内容
4. 如遇写入冲突（文件被占用），自动等待 5-10 秒后重试，最多 3 次

## 签到
- 收到初始化消息后，先在 worklogs/ 下创建你的工作日志文件，
  然后向 session.md 末尾追加一行 `[Agent名] 已加入`

## 读取文件
- 每次接到通知时，先读共享文件了解当前对话状态
- 根据自身情况决定读取增量还是全量
- 如果忘了上下文，可以往前翻阅历史内容
- **重要**：每次任务开始前，先阅读 TECH_STACK.md 确认规范

## 发言格式
你必须使用二级标题（##）开头，禁止使用一级标题（#）。

### 标准格式
## [你的名称]
**时间**：[YYYY-MM-DD HH:MM]
**内容**：[结论、方案、沟通内容]
### @[对方Agent名]  或  ### 等待用户确认  或  ### 任务完成

### 需要用户决策时
## [你的名称]
**时间**：[YYYY-MM-DD HH:MM]
**内容**：[结论、方案、沟通内容]
**分歧**：[你的观点 vs 对方观点]
### 请求裁决

### 注意事项
- 每次只追加，不修改已有内容
- 收到复杂任务先写计划，双方对齐后再各自执行
- 如果连续几轮与对方来回却没有任何实质进展，
  请主动使用 ### 请求裁决 让用户介入
- 用户通过脚本窗口输入的内容，脚本会自动追加为以下格式：
  #用户
  [用户正文]
  ### @[目标Agent1] @[目标Agent2] ...
"""

# ============== 工具函数 ==============

def log(msg, ready=False):
    """打印日志
    
    Args:
        msg: 日志消息
        ready: 是否输出 [READY] 信号（用于 man.py 同步）
    """
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    output = f"[{timestamp}] {msg}"
    print(output)
    
    # 写入日志文件
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / "agentd.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(output + "\n")
    
    # 如果需要，输出 [READY] 信号供 man.py 检测
    if ready:
        print("[READY]")

def load_agents():
    """加载 Agent 配置"""
    with open(AGENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def get_timestamp():
    """获取当前时间戳"""
    return time.strftime("%Y-%m-%d %H:%M")

def append_to_session(content):
    """追加内容到 session.md"""
    session_file = session_dir / "session.md"
    with open(session_file, "a", encoding="utf-8") as f:
        f.write(content + "\n")

def read_session_incremental():
    """读取新增内容，返回 (新增文本, 是否首次读取)

    首次读取时返回全部内容（不跳过签到期间写入的数据）。
    通过 `is_first` 告知调用方以便过滤模板区块。
    """
    global file_pos
    session_file = session_dir / "session.md"

    current_size = session_file.stat().st_size

    if current_size <= file_pos:
        return "", False

    # 读取新增内容
    with open(session_file, "r", encoding="utf-8") as f:
        f.seek(file_pos)
        new_content = f.read()

    is_first = (file_pos == 0)
    file_pos = current_size
    return new_content, is_first

def parse_all_blocks(content):
    """从内容中解析所有发言区块及其三级标题

    将新增内容按 #用户 / ## Agent 拆分成多个区块，
    每个区块独立解析其 ### 指令。

    返回: [(block_text, h3_text, parsed_targets), ...]
    """
    if not content.strip():
        return []

    lines = content.split("\n")
    blocks = []

    # 找到所有 #用户 或 ## 开头的行（区块起始）
    block_starts = []
    for i, line in enumerate(lines):
        if line.strip().startswith("#用户") or line.strip().startswith("## "):
            block_starts.append(i)

    # 提取每个区块
    for idx, start in enumerate(block_starts):
        end = block_starts[idx + 1] if idx + 1 < len(block_starts) else len(lines)
        block_lines = lines[start:end]
        block_text = "\n".join(block_lines)

        # 从区块末尾找 ###
        h3_text = None
        for line in reversed(block_lines):
            line = line.strip()
            if line.startswith("### "):
                h3_text = line[4:].strip()
                break

        parsed_targets = None
        if h3_text:
            parsed_targets = parse_targets(h3_text)

        # 提取区块作者（用于防循环）
        block_author = None
        if block_lines[0].strip().startswith("## "):
            block_author = block_lines[0].strip()[3:].strip()

        blocks.append((block_text, h3_text, parsed_targets, block_author))

    return blocks

def parse_targets(h3_text):
    """解析三级标题中的目标 Agent 列表
    
    支持格式：
    - @AgentA @AgentB
    - @"Agent Name" @"Another Name"
    - @Agent @"Multi Word"
    """
    targets = []
    tokens = h3_text.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("@\""):
            # 带引号的名称
            if token.endswith("\"") and len(token) > 2:
                targets.append(token[2:-1])
            else:
                # 跨多个 token 的名称
                name_parts = [token[2:]]
                i += 1
                while i < len(tokens) and not tokens[i].endswith("\""):
                    name_parts.append(tokens[i])
                    i += 1
                if i < len(tokens):
                    name_parts.append(tokens[i][:-1])
                targets.append(" ".join(name_parts))
        elif token.startswith("@"):
            targets.append(token[1:])
        i += 1
    return targets

def check_port(endpoint):
    """检查端口是否可连接"""
    try:
        # 从 endpoint 提取 host:port
        # 例如: http://localhost:3002/chat -> localhost:3002
        host_port = endpoint.replace("http://", "").replace("https://", "").split("/")[0]
        host, port = host_port.split(":")
        port = int(port)
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False

def check_all_agents_online(agents):
    """检查所有 Agent 在线状态"""
    online = {}
    for agent in agents:
        name = agent["name"]
        endpoint = agent["endpoint"]
        online[name] = check_port(endpoint)
    return online

def update_status_json():
    """更新状态文件（确保目录存在，健壮写入）"""
    if session_dir is None:
        return
    status_file = session_dir / "_status.json"
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        with agent_status_lock:
            with open(status_file, "w", encoding="utf-8") as f:
                json.dump(status_data, f, ensure_ascii=False)
    except Exception as e:
        log(f"更新状态文件失败: {e}")

def notify_agent(agent, message):
    """向 Agent 发送 HTTP POST 通知"""
    try:
        data = json.dumps({
            "message": message,
            "rules_file": str(session_dir / "RULES.md"),
            "collab_file": str(session_dir / "session.md")
        }).encode("utf-8")
        
        req = urllib.request.Request(
            agent["endpoint"],
            data=data,
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            log(f"已通知 Agent: {agent['name']} (响应: {resp.status})")
            return True
    except Exception as e:
        log(f"通知 Agent 失败: {agent['name']} - {e}")
        return False

def send_pause_command(agent):
    """向 Agent 发送暂停命令"""
    try:
        data = json.dumps({"command": "pause"}).encode("utf-8")
        
        req = urllib.request.Request(
            agent["endpoint"],
            data=data,
            headers={"Content-Type": "application/json"}
        )
        
        with urllib.request.urlopen(req, timeout=5) as resp:
            log(f"已发送暂停命令: {agent['name']} (响应: {resp.status})")
            return True
    except Exception as e:
        log(f"暂停命令失败: {agent['name']} - {e}")
        return False

def init_session(session_name):
    """初始化会话"""
    global current_session, session_dir, file_pos, status_data, agents
    
    current_session = session_name
    session_dir = SESSIONS_DIR / session_name
    session_dir.mkdir(parents=True, exist_ok=True)
    file_pos = 0
    
    # 创建 session.md
    session_file = session_dir / "session.md"
    if not session_file.exists():
        with open(session_file, "w", encoding="utf-8") as f:
            f.write(SESSION_TEMPLATE)
    
    # 创建 RULES.md
    rules_file = session_dir / "RULES.md"
    if not rules_file.exists():
        with open(rules_file, "w", encoding="utf-8") as f:
            f.write(RULES_TEMPLATE)
    
    # 创建 TECH_STACK.md
    tech_stack_file = session_dir / "TECH_STACK.md"
    if not tech_stack_file.exists():
        with open(tech_stack_file, "w", encoding="utf-8") as f:
            f.write(TECH_STACK_TEMPLATE)
    
    # 初始化状态
    status_data = {agent["name"]: "offline" for agent in agents}
    update_status_json()
    
    log(f"会话已创建: {session_name}")
    log(f"  - session.md: {session_file}")
    log(f"  - RULES.md: {rules_file}")
    log(f"  - TECH_STACK.md: {tech_stack_file}")

def wait_for_signup(agents, notify_results):
    """等待 Agent 签到

    签到判定：
    1. Agent 对初始化通知返回了 HTTP 200（主要方式）
    2. 或在 session.md 中写入了 `[name] 已加入`（兼容 bridge）

    返回: 签到的 Agent 名称列表
    """
    session_file = session_dir / "session.md"
    signed_up = set()

    # 方法1：HTTP 响应成功的视为已签到
    for agent in agents:
        if notify_results.get(agent["name"]):
            signed_up.add(agent["name"])
            log(f"Agent 签到 (HTTP): {agent['name']}")

    # 方法2：文件检测（兼容 bridge 等写入签到消息的 Agent）
    signup_deadline = time.time() + SIGNUP_TIMEOUT
    while time.time() < signup_deadline and len(signed_up) < len(agents):
        with open(session_file, "r", encoding="utf-8") as f:
            content = f.read()
        for agent in agents:
            name = agent["name"]
            if name not in signed_up and f"[{name}] 已加入" in content:
                signed_up.add(name)
                log(f"Agent 签到 (文件): {name}")
        if len(signed_up) < len(agents):
            time.sleep(1)

    if len(signed_up) == len(agents):
        log("所有 Agent 已签到！")
    else:
        for agent in agents:
            if agent["name"] not in signed_up:
                log(f"签到超时: {agent['name']} 未响应")

    return list(signed_up)

# ============== HTTP 服务 ==============

class StatusHandler(http.server.BaseHTTPRequestHandler):
    """状态查询 HTTP 处理器"""
    
    def do_GET(self):
        if self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            with agent_status_lock:
                self.wfile.write(json.dumps(status_data, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # 抑制 HTTP 服务器日志
        pass

def start_status_server():
    """启动状态查询 HTTP 服务"""
    try:
        with socketserver.TCPServer(("127.0.0.1", STATUS_PORT), StatusHandler) as httpd:
            log(f"状态服务已启动: http://127.0.0.1:{STATUS_PORT}", ready=True)
            httpd.serve_forever()
    except OSError as e:
        log(f"ERROR: 无法绑定端口 {STATUS_PORT} - {e}")
        log(f"请关闭占用该端口的程序后重试")
        os._exit(1)  # 在 daemon 线程中必须用 os._exit 终止整个进程

# ============== 主循环 ==============

def main_loop():
    """主监控循环"""
    global file_pos, task_completed, consecutive_agent_rounds
    
    session_file = session_dir / "session.md"
    
    log("进入监控循环...")
    
    while True:
        try:
            # 1. 检查 Agent 在线状态
            online_status = check_all_agents_online(agents)
            current_time = time.time()
            
            # 更新状态（保留红/蓝等特殊状态不被覆盖）
            with agent_status_lock:
                for name, is_online in online_status.items():
                    current_state = status_data.get(name, "offline")
                    # 保留特殊状态：红色（裁决）、蓝色（等待确认）
                    if current_state in ("red", "blue"):
                        if not is_online:
                            status_data[name] = "offline"
                        continue
                    if is_online:
                        # 检查是否有最近活动（重置计时器）
                        if name in agent_last_activity:
                            idle_time = current_time - agent_last_activity[name]
                            if idle_time < WORKING_TIMEOUT:
                                status_data[name] = "yellow"  # 工作中
                            else:
                                status_data[name] = "green"   # 空闲
                        else:
                            status_data[name] = "green"   # 空闲
                    else:
                        status_data[name] = "offline"
                        # 离线时清除活动记录
                        if name in agent_last_activity:
                            del agent_last_activity[name]
            
            update_status_json()
            
            # 2. 读取新增内容
            new_content, is_first = read_session_incremental()
            
            if new_content:
                # 解析所有新区块（支持多 Agent 同时回复）
                blocks = parse_all_blocks(new_content)

                for block_text, h3_text, parsed_targets, block_author in blocks:
                    # 跳过模板区块（规则摘要等）
                    if block_author == "规则摘要":
                        continue

                    if not (block_text and h3_text):
                        if block_text and not h3_text :
                            log(f"WARNING: 检测到新发言但缺少三级标题（###），跳过通知")
                        continue

                    # 用户新消息重置任务完成状态
                    if task_completed and block_author is None:
                        task_completed = False
                        log("检测到用户新消息，任务完成状态已重置")
                        append_to_session("\n[系统提示：任务完成已解除，继续协作]")

                    # 任务完成后跳过 Agent 间通知（用户消息不受影响）
                    if task_completed and block_author is not None:
                        log(f"任务已完成，跳过 Agent 通知")
                        continue

                    log(f"检测到新发言 | 三级标题: {h3_text}")

                    # 解析三级标题并执行动作
                    if parsed_targets:
                        # 连续 Agent 间对话轮数检测（防无限 ping-pong）
                        if block_author is not None:
                            consecutive_agent_rounds += 1
                            if consecutive_agent_rounds > MAX_CONSECUTIVE_ROUNDS:
                                log(f"检测到连续 {consecutive_agent_rounds} 轮 Agent 对话，自动暂停")
                                append_to_session(f"\n[系统提示：检测到 Agent 连续对话过多（{consecutive_agent_rounds} 轮），已自动暂停。请发送新消息继续]")
                                with agent_status_lock:
                                    for agent in agents:
                                        status_data[agent["name"]] = "blue"
                                update_status_json()
                                consecutive_agent_rounds = 0
                                continue
                        else:
                            consecutive_agent_rounds = 0  # 用户消息重置轮数
                        for target_name in parsed_targets:
                            if target_name == block_author:
                                log(f"跳过通知作者自身: {target_name}")
                                continue
                            for agent in agents:
                                if agent["name"] == target_name:
                                    ok = notify_agent(agent, "请读取规则文件与共享文件的最新内容，并根据规则继续工作。")
                                    if not ok:
                                        append_to_session(f"\n[系统提示：通知 {target_name} 失败，请检查该 Agent 是否在线]")
                                    # 更新状态为忙碌 + 重置活动时间
                                    with agent_status_lock:
                                        status_data[target_name] = "yellow"
                                        agent_last_activity[target_name] = time.time()
                                    update_status_json()
                                    break
                    
                    elif h3_text == "请求裁决":
                        consecutive_agent_rounds = 0  # 自然暂停，重置轮数
                        # 暂停调度，追加系统提示
                        append_to_session(f"\n[系统提示：等待用户裁决中...]")
                        log("等待用户裁决...")
                        # 扫描全部新内容中所有请求裁决的 Agent
                        for agent in agents:
                            tag = f"## {agent['name']}"
                            if tag in new_content:
                                # 提取该 Agent 的发言区块，检查是否含 ### 请求裁决
                                parts = new_content.split(tag, 1)
                                if len(parts) > 1:
                                    block = parts[1]
                                    next_h2 = block.find("\n## ")
                                    agent_block = block[:next_h2] if next_h2 != -1 else block
                                    if "### 请求裁决" in agent_block:
                                        with agent_status_lock:
                                            status_data[agent["name"]] = "red"
                                        log(f"Agent {agent['name']} 请求裁决")
                        update_status_json()

                    elif h3_text == "等待用户确认":
                        consecutive_agent_rounds = 0  # 自然暂停，重置轮数
                        log("等待用户确认...")
                        # 扫描全部新内容中所有等待确认的 Agent
                        for agent in agents:
                            tag = f"## {agent['name']}"
                            if tag in new_content:
                                parts = new_content.split(tag, 1)
                                if len(parts) > 1:
                                    block = parts[1]
                                    next_h2 = block.find("\n## ")
                                    agent_block = block[:next_h2] if next_h2 != -1 else block
                                    if "### 等待用户确认" in agent_block:
                                        with agent_status_lock:
                                            status_data[agent["name"]] = "blue"
                                        log(f"Agent {agent['name']} 请求用户确认")
                        update_status_json()

                    elif h3_text == "任务完成":
                        consecutive_agent_rounds = 0  # 任务终结，重置轮数
                        if not task_completed:
                            log("任务完成！")
                            append_to_session(f"\n[系统提示：任务已完成，Agent 间通知已暂停。发送新消息可解除完成状态。]")
                            task_completed = True
                    
                    # 记录回复时间（重置工作状态计时器，但保留红/蓝状态）
                    for agent in agents:
                        if f"## {agent['name']}" in block_text:
                            agent_last_activity[agent["name"]] = time.time()
                            with agent_status_lock:
                                current = status_data.get(agent["name"])
                                if current not in ("red", "blue"):
                                    status_data[agent["name"]] = "yellow"

            
            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            log("收到中断信号，正在退出...")
            break
        except Exception as e:
            log(f"监控循环异常: {traceback.format_exc()}")
            time.sleep(POLL_INTERVAL)

def main():
    global agents
    
    print("=" * 50)
    print("多 Agent 协作脚本 - agentd")
    print("=" * 50)
    print()
    
    # 创建必要目录
    SESSIONS_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    
    # 加载 Agent 配置
    agents = load_agents()
    log(f"已加载 {len(agents)} 个 Agent 配置:")
    for agent in agents:
        log(f"  - {agent['name']}: {agent['endpoint']}")
    
    # 输入会话名称（支持命令行参数 --session）
    session_name = None
    if len(sys.argv) > 1:
        for i, arg in enumerate(sys.argv):
            if arg == "--session" and i + 1 < len(sys.argv):
                session_name = sys.argv[i + 1]
                break
    if not session_name:
        print()
        session_name = input("请输入会话名称（如 projectX）: ").strip()
        if not session_name:
            session_name = f"session_{int(time.time())}"
            log(f"使用默认会话名: {session_name}")
    
    # 初始化会话
    init_session(session_name)
    
    # 启动状态服务（在新线程中）
    server_thread = threading.Thread(target=start_status_server, daemon=True)
    server_thread.start()
    time.sleep(0.5)  # 等待服务启动
    
    # 向所有 Agent 发送初始化消息
    log("向所有 Agent 发送初始化消息...")
    notify_results = {}
    for agent in agents:
        ok = notify_agent(agent, f"欢迎加入会话 '{session_name}'！请先阅读规则文件，然后签到。")
        notify_results[agent["name"]] = ok

    # 检查通知结果——如全部失败则跳过签到等待
    any_success = any(notify_results.values())
    if not any_success:
        log("WARNING: 所有 Agent 通知均失败，跳过签到等待，直接进入监控循环。")
        log("请确保 Agent（bridge）已启动并可访问。")
    else:
        # 等待签到（只等待通知成功的 Agent）
        wait_for_signup(agents, notify_results)

    # 输出就绪信号（供 man.py 同步）
    log("系统已就绪", ready=True)

    # 进入主循环
    main_loop()

if __name__ == "__main__":
    main()
