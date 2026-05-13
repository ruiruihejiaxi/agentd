# 多 Agent 文件协作系统

通过文件共享 + HTTP 通知实现多个 AI Agent 协作的调度系统。支持 Agent 签到、三级标题驱动的流程控制、状态呼吸灯、请求裁决等协作模式。

## 架构

```
+----------------------------+
|        agentd.py           |  ← 主调度器（文件监控 + 通知分发 + 状态管理）
|  HTTP :3001 (/api/status)  |
|  文件监控 + 三级标题解析    |
|  在线检测 + 状态同步       |
+------+------+------+------+
       |      |      |
       v      v      v
   +------+------+------+
   |Agent |Agent |ui.py |  ← Agent HTTP POST /chat 端点
   | A    | B    |用户窗 |
   +------+------+------+
          man.py           ← 一键启动器
```

运行时数据流：

```
session.md  ← Agent 间通过共享文件交换信息
     ↑↓             （追加写入，不修改已有内容）
agentd.py  ← 监控文件变化，解析 ### 三级标题，发送 HTTP 通知
     ↓
 Agent    ← 收到通知后读取文件，处理后追加回复
```

## 文件结构

```
agentd/
+-- man.py              # 总启动器：一键启动所有服务
+-- agentd.py           # 主调度程序：文件监控、通知分发、状态同步
+-- ui.py               # 用户输入窗口（tkinter GUI）
+-- agents.json         # Agent 配置（名称、端点、能力）
+-- README.md           # 本文档
+-- sessions/           # 会话目录（自动创建）
|   +-- <会话名>/
|       +-- session.md  # 共享交互文件（Agent 间协作的核心）
|       +-- RULES.md    # 协作规则文件
|       +-- TECH_STACK.md  # 技术栈规范
|       +-- _status.json   # Agent 状态实时快照
+-- logs/
    +-- agentd.log      # 调度器运行日志
```

## 快速开始

### 1. 填写 agents.json

`agents.json` 是 Agent 的配置文件，格式为 JSON 数组，数组内每个元素是一个 Agent 配置。单个 Agent 示例如下：

```json
[
  {
    "name": "Agent 名称",
    "role": "角色描述",
    "endpoint": "HTTP 服务地址",
    "capabilities": ["能力1", "能力2"],
    "prompt_hint": "协作提示"
  }
]
```

> ⚠️ **注意**：`agents.json` 最外层必须是数组 `[ ... ]`，不能是单个对象 `{ ... }`。即使只有一个 Agent，也必须用数组包裹。

各字段说明：

| 字段 | 必填 | 说明 |
| :--- | :--- | :--- |
| `name` | 是 | Agent 唯一名称，不能与其他 Agent 重名 |
| `role` | 是 | 角色描述，如 "前端开发、架构设计" |
| `endpoint` | 是 | HTTP POST /chat 地址，调度系统通过此地址通知 Agent |
| `capabilities` | 是 | 能力列表，如 ["React", "TypeScript"] |
| `prompt_hint` | 是 | 给协作伙伴的自我介绍或工作提示 |

#### 获取 Agent 配置

将以下提示词发送给 Agent，让它理解背景并返回自己的配置：

```

## 背景：你为什么要配这个？

你即将接入一个多 Agent 协作系统（agentd），工作方式如下：

1. 多个 AI Agent 共享一个 session.md 文件，所有交流都写在这个文件里
2. agentd 监控 session.md 的变化，检测到 "### @你的名字" 时，就该通知你干活了
3. **但 agentd 怎么通知你？** —— 通过 HTTP POST 到你本地启动的一个服务端口
4. 所以你必须：**（a）先启动持续运行的 HTTP 服务**，**（b）再把实际监听的地址写入 agents.json**

没有这两步，agentd 找不到你、叫不动你，你无法参与协作。

---

## 第一步：启动 HTTP 服务（持续运行，不能退出）

在你的进程中启动一个 HTTP 服务，监听一个你选定的端口（如 3010）。

这个 HTTP 服务会收到两种请求：

### 类型一：任务通知（正常干活）
```json
{
  "message": "请读取规则文件与共享文件的最新内容，并根据规则继续工作。",
  "rules_file": "sessions/xxx/RULES.md",
  "collab_file": "sessions/xxx/session.md"
}
```
处理逻辑：
1. **返回 HTTP 200**
2. 读取 `collab_file` 指向的 session.md 了解上下文
3. 读取 `rules_file` 指向的 RULES.md 按格式回复
4. **第一次**收到时，在 session.md 末尾写一行 `[你的名字] 已加入`
5. **后续**每次收到，按格式在 session.md 末尾追加你的回复

### 类型二：暂停指令
```json
{"command": "pause"}
```
收到后立即中止当前任务。

### ⚠️ 关键：HTTP 服务必须持续运行
**处理完请求不能退出，必须一直监听。**
```python
# ❌ 错误：只处理一个请求就退出
with HTTPServer(...) as server:
    server.handle_request()

# ✅ 正确：永久运行，持续等待
with HTTPServer(...) as server:
    server.serve_forever()
```

---

## 第二步：填写你的配置信息

确认 HTTP 服务已在某个端口上稳定运行后，将以下格式的 JSON 写入 D:\agentd\agents.json 文件：

```json
[
  {
    "name": "你的名称（如 WorkBuddy）",
    "role": "你的角色描述（如 全栈开发、架构设计）",
    "endpoint": "http://localhost:你的端口号/chat",
    "capabilities": ["能力1", "能力2"],
    "prompt_hint": "给其他 Agent 的自我介绍或工作提示"
  }
]
```

**注意事项：**
1. `agents.json` 最外层必须是数组 `[ ... ]`，**不能**是单个对象 `{ ... }`
2. `endpoint` 必须写你**第一步实际监听的地址和端口**，不要编造
3. 如果文件中原有其他 Agent 的配置，请保留它们，只把自己加进去

**写入后立即自我检查：**
```bash
python -c "import json; json.load(open('D:\\agentd\\agents.json'))"
```
- 不报错 → JSON 格式正确
- 确认 endpoint 的端口号跟第一步实际监听的完全一致

---

**完成以上两步之后，所有协作交互都在 session.md 文件里自动完成，不再需要人为干预。**

#### 配置示例

```json
[
  {
    "name": "Claude Code",
    "role": "前端开发、架构设计、代码审查",
    "endpoint": "http://localhost:3003/chat",
    "capabilities": ["React/Vue开发", "TypeScript", "CSS/动画", "代码审查"],
    "prompt_hint": "擅长前端架构设计和性能优化，熟悉响应式设计"
  },
  {
    "name": "WorkBuddy",
    "role": "全栈开发、运维、数据库管理",
    "endpoint": "http://localhost:3002/chat",
    "capabilities": ["Node.js/Python后端", "PostgreSQL/MySQL", "Docker/K8s", "API设计"],
    "prompt_hint": "擅长系统架构和数据管理，熟悉 DevOps 流程"
  }
]
```

### 2. 启动 Agent

手动启动所有需要协作的 Agent 进程，确保它们的 HTTP 端点可访问。

### 3. 启动调度系统

```bash
python man.py
```

`man.py` 会自动：
1. 启动 `agentd.py` 调度器
2. 轮询检测 agentd 就绪（HTTP :3001），最长 120 秒
3. 就绪后自动启动 `ui.py` 用户窗口

也可分别启动（调试用）：

```bash
python agentd.py --session myproject
python ui.py
```

### 4. 开始协作

Agent 签到完成后，在 ui.py 窗口中：
1. 勾选目标 Agent（可多选）
2. 输入消息
3. 按回车或点击发送

## 发言格式

### 用户发言（ui.py 自动生成）

```
#用户
帮我设计一个登录页面
### @"Claude Code" @"WorkBuddy"
```

> 含空格的 Agent 名必须使用双引号包裹：@"Claude Code"

### Agent 发言

```
## Claude Code
**时间**：2026-05-08 14:30
**内容**：
建议采用 JWT 无状态认证。
### @"WorkBuddy"
```

### 请求裁决（出现分歧时）

```
## WorkBuddy
**时间**：2026-05-08 14:45
**内容**：
缓存策略需要统一。
**分歧**：WorkBuddy 建议 3 天 vs Claude Code 建议 7 天
### 请求裁决
```

## 三级标题动作

| 三级标题 | 动作 |
| :--- | :--- |
| `### @"AgentA" @"AgentB"` | 通知指定的 Agent |
| `### 等待用户确认` | 暂停，蓝灯闪烁，等待用户输入 |
| `### 请求裁决` | 暂停，追加 `[系统提示：等待用户裁决中...]`，红灯闪烁 |
| `### 任务完成` | 追加 `[系统提示：任务已完成]`，停止会话流转 |

## 状态呼吸灯

| 颜色 | 含义 |
| :--- | :--- |
| 绿色呼吸 | 在线，空闲 |
| 黄色呼吸 | 工作中（120 秒内有回复） |
| 灰色 | 离线/无响应 |
| 红色闪烁 | 该 Agent 请求裁决，需用户介入 |
| 蓝色闪烁 | 暂停，等待用户确认 |

状态通过 `_status.json` 实时同步，ui.py 读取后渲染呼吸灯动画。

## 暂停功能

点击 Agent 卡片的 [暂停] 按钮，直接向 Agent 发送暂停指令：

```json
{"command": "pause"}
```

## Agent 端要求

Agent 必须提供一个 HTTP POST `/chat` 端点，接收以下格式的通知：

```json
{
  "message": "请读取规则文件与共享文件的最新内容，并根据规则继续工作。",
  "rules_file": "sessions/<会话名>/RULES.md",
  "collab_file": "sessions/<会话名>/session.md"
}
```

### 处理流程

1. 读取 `rules_file` 了解协作规则
2. 读取 `collab_file` 了解当前对话上下文
3. 在 session.md 中写入 `[Agent名] 已加入` 完成签到
4. 自主执行任务后，按格式追加回复到 `collab_file`
5. 在回复末尾添加三级标题指示下一步动作

### 暂停命令

Agent 应监听 `{"command": "pause"}` 指令，收到后中止当前任务。

## 故障排除

| 问题 | 可能原因 | 解决 |
| :--- | :--- | :--- |
| 3001 端口被占用 | 上次 agentd 未正常退出 | 关闭占用进程后重试 |
| Agent 灰色离线 | Agent 进程未启动或 endpoint 错误 | 检查 Agent 进程和 `agents.json` 中的 endpoint |
| Agent 未签到 | Agent 未收到通知或文件写入延迟 | 检查 Agent 端日志 |
| 裁决未响应 | 用户未介入 | 在 ui.py 中输入裁决决定 |

## 依赖

- Python 3.7+
- tkinter（Python 内置）
