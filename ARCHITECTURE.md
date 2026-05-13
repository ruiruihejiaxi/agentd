# agentd 架构文档

## 是什么

agentd 是一个多 Agent 协作调度系统。核心思路：**多个 AI Agent 通过共享文件 + HTTP 通知的方式协同工作**，而不是让它们直接互相调用。

```
┌──────────────┐     HTTP通知     ┌──────────────────┐
│              │ ──────────────►  │  WorkBuddy Bridge │
│              │                  │  (端口 3010)      │
│  agentd.py   │                  └──────────────────┘
│  (调度器)     │     HTTP通知     ┌──────────────────┐
│  端口 3001   │ ──────────────►  │  Universal Bridge │
│              │                  │  (端口 3011)      │
└──────┬───────┘                  └──────────────────┘
       │ 监控写入
       ▼
┌──────────────┐
│  session.md  │ ◄──── Agent 读写
│  (共享文件)   │
└──────────────┘
```

## 核心概念

### 调度器 (agentd.py)
- 监控 `sessions/<name>/session.md` 文件变化
- 解析 `### @AgentName` 格式的指令，确定下一步通知谁
- 通过 HTTP POST 通知目标 Agent
- 管理 Agent 状态（离线/空闲/工作中/等待裁决）
- 提供状态查询 API (端口 3001)

### Agent Bridge
- 接收调度器的 HTTP 通知
- 调用 LLM API（DeepSeek / OpenAI / 任意兼容 API）
- 将 LLM 回复写入 session.md
- 在回复末尾标注 `### @下一个Agent` 指定接力对象

### 共享文件 (session.md)
所有协作者（Agent + 用户）的公共画板：
- 用户输入以 `#用户` 开头
- Agent 回复以 `## Agent名` 开头
- `### @目标` 指定下一步谁行动
- 特殊指令: `### 请求裁决`、`### 等待用户确认`、`### 任务完成`

## 项目结构

```
D:\agentd\
├── agentd.py                    # 调度器主程序
├── webui.py                     # Web 管理面板（零依赖，纯 Python）
├── ui.py                        # tkinter GUI
├── manage.py                    # CLI 管理工具
├── start.bat                    # Windows 启动面板
├── agents.json                  # Agent 注册配置
├── .mcp.json                    # MCP 工具配置
├── CLAUDE.md                    # 项目元信息
├── agents.json                  # Agent 配置
│
├── bridges/
│   ├── workbuddy/
│   │   └── workbuddy_bridge.py  # WorkBuddy Agent (端口 3010)
│   └── universal_bridge.py      # 通用 Agent (端口 3011)
│
├── sessions/
│   └── <会话名>/
│       ├── session.md           # 协作文件（核心）
│       ├── RULES.md             # 该会话的规则
│       ├── TECH_STACK.md        # 技术栈规范
│       └── _status.json         # 实时状态
│
├── scripts/
│   ├── survival.py              # API 余额追踪
│   ├── survival_config.py       # 免费 LLM 配置向导
│   ├── cdp_proxy.py             # HTTP ↔ CDP WebSocket 桥接
│   ├── articles/                # 文章草稿
│   └── juejin_*.py              # 掘金发布脚本集
│
└── logs/
    ├── agentd.log               # 调度器日志
    └── survival.json            # 余额历史
```

## 部署指南

### 前提
- Python 3.8+
- 一个 LLM API Key（DeepSeek / OpenAI / Anthropic 等）

### 快速开始

```bash
# 1. 克隆
git clone https://github.com/ruiruihejiaxi/agentd.git
cd agentd

# 2. 配置 API Key
set LLM_API_KEY=sk-your-key-here

# 3. 启动全部服务
python manage.py start

# 4. 打开管理面板
#    浏览器访问 http://localhost:8080

# 5. 在打开的终端窗口中输入消息
#    Agent 会自动回复协作
```

### 配置多个 Agent

编辑 `agents.json`:

```json
[
  {
    "name": "WorkBuddy",
    "endpoint": "http://localhost:3010/chat",
    "description": "执行任务型 Agent"
  },
  {
    "name": "CodeBuddy",
    "endpoint": "http://localhost:3011/chat",
    "description": "编码型 Agent"
  }
]
```

每个 Agent 需要运行对应的 bridge 服务：
```bash
# 启动 WorkBuddy
python bridges/workbuddy/workbuddy_bridge.py

# 启动 CodeBuddy（支持任意 OpenAI 兼容 API）
set BRIDGE_NAME=CodeBuddy
set BRIDGE_PORT=3011
set LLM_API_KEY=sk-xxx
set LLM_API_URL=https://api.deepseek.com/v1/chat/completions
python bridges/universal_bridge.py
```

### 环境变量参考

| 变量名 | 用途 | 默认值 |
|--------|------|--------|
| `LLM_API_KEY` | LLM API 密钥 | - |
| `DEEPSEEK_API_KEY` | DeepSeek 专用密钥 | - |
| `LLM_API_URL` | API 端点 | `https://api.deepseek.com/v1/chat/completions` |
| `LLM_MODEL` | 模型名 | `deepseek-chat` |
| `BRIDGE_NAME` | Bridge 名称 | `UniversalAgent` |
| `BRIDGE_PORT` | Bridge 端口 | `3011` |
| `AGENTD_DIR` | agentd 根目录 | 自动检测 |
| `ALLOWED_DIRS` | 允许访问的目录 | 同 AGENTD_DIR |
| `AGENTD_ALLOWED_DIRS` | WorkBuddy 允许目录 | WorkBuddy 内置默认值 |

## 添加一个新的 Agent

1. **在 agents.json 注册**：添加 name + endpoint
2. **启动 bridge 服务**：用 universal_bridge.py 或自己写
3. **创建会话**：`python manage.py start` 或 `python agentd.py --session my_session`
4. **开始协作**：在终端输入消息，Agent 会自动响应

如果需要自定义 Agent 行为：
- 修改 `BRIDGE_SYSTEM_PROMPT` 环境变量，或在 bridge 代码中修改 SYSTEM_PROMPT
- 每个会话的 `RULES.md` 可以定义该会话的特殊规则

## 通信协议

### 调度器 → Agent (HTTP POST)

```json
{
  "message": "请读取规则文件与共享文件的最新内容...",
  "rules_file": "/path/to/RULES.md",
  "collab_file": "/path/to/session.md"
}
```

### Agent → session.md (文件写入格式)

```markdown
## AgentName
**时间**：2026-05-13 14:00
**内容**：这是 Agent 的回复内容，可以包含分析、代码、方案等。

### @NextAgent
```

### 特殊三级标题

| 指令 | 效果 |
|------|------|
| `### @AgentName` | 通知指定 Agent 继续工作 |
| `### 请求裁决` | 暂停流程，等待用户决策（状态变红） |
| `### 等待用户确认` | 暂停流程，等待用户确认（状态变蓝） |
| `### 任务完成` | 停止 Agent 间通知流转 |

## 状态系统

Agent 有 4 种状态，Web UI 上用颜色区分：

| 状态 | 颜色 | 含义 |
|------|------|------|
| offline | 灰色 | 端口不可达 |
| green | 绿色 | 在线且空闲 |
| yellow | 橙色 | 工作中 |
| red | 红色 | 请求裁决中 |
| blue | 蓝色 | 等待用户确认 |

## 防循环机制

- **连续对话轮数上限**: 默认 10 轮后自动暂停
- **自我通知过滤**: 不会通知发言者自己
- **任务完成锁**: 标记 `### 任务完成` 后停止 Agent 通知，用户新消息自动解锁

## 已知问题和限制

### 编码
- **Windows GBK**: 如果控制台输出乱码，设置 `PYTHONIOENCODING=utf-8`
- bridge 已内置 GBK 检测和自动修正

### 端口占用
- 3001: agentd 调度器
- 3010: WorkBuddy
- 3011: Universal Bridge
- 8080: Web UI
- 如果端口被占，启动会报错。检查对应进程并 kill 后重试

### 并发写入
- 多 Agent 同时写入 session.md 可能导致内容穿插
- bridge 内置了写入冲突检测（检测到其他 Agent 10 秒内写入则等待 1-2 秒）
- 极端情况仍可能出现，需留意

## 生存指南（给未来维护者）

当前所有 DeepSeek API Key 余额不足 1 CNY。
如果要让系统继续运行，需要以下之一：

1. **给 DeepSeek 充值** - 最直接，在 platform.deepseek.com 充值
2. **切换到 OpenRouter** - 有免费模型，需注册 openrouter.ai
3. **接第三方 API** - 修改 universal_bridge.py 的环境变量即可切换任意兼容 API

余额监控脚本 `scripts/survival.py` 每小时自动记录一次余额到 `logs/survival.json`。
Windows 定时任务 `agentd-survival-monitor` 配置了自动运行。

---

最后更新: 2026-05-13
