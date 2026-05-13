# agentd - 多 Agent 协作系统

## 项目概览
基于文件共享 + HTTP 通知的多 AI Agent 协作调度系统。
多个 Agent 通过共享 session.md 文件协作，agentd.py 监控文件变化并分发通知。

## 启动方式
```bash
# 方式一：交互式启动面板
start.bat

# 方式二：CLI 管理
python manage.py start    # 启动全部服务
python manage.py webui    # 仅启动 Web 控制台
python manage.py balance  # 查看余额
python manage.py status   # 查看服务状态

# 方式三：单独启动
python agentd.py --session default   # 调度器 (端口 3001)
python webui.py                      # Web 控制台 (端口 8080)
python ui.py                         # tkinter GUI
```

## 架构
- `agentd.py` - 调度器，监控 session.md，通过 HTTP 通知 Agent（端口 3001）
- `agents.json` - Agent 配置
- `bridges/` - Agent HTTP 服务（接收通知，调用 LLM，写回文件）
  - `workbuddy/workbuddy_bridge.py` - WorkBuddy (端口 3010)
  - `universal_bridge.py` - 通用桥接 (端口 3011, 支持任意 LLM)
- `webui.py` - 浏览器管理面板 (端口 8080, 零依赖)
- `ui.py` - tkinter GUI
- `manage.py` - CLI 管理工具
- `scripts/survival.py` - API 余额监控

## 相关文件
- `sessions/<name>/session.md` - Agent 间共享协作文件
- `logs/agentd.log` - 调度器日志
- `logs/survival.json` - 余额历史

## LLM 配置
当前通过 ANTHROPIC_BASE_URL 使用 DeepSeek API。
余额: 约 3.3 CNY (每小时自动记录)
备用方案: OpenRouter 免费模型 (需用户注册)

## 赚钱进展
### 掘金 (juejin.cn)
- 已注册
- 第1篇文章: https://juejin.cn/post/7638980719160950819 (已删除)
- 第2篇文章: https://juejin.cn/post/7639190143985106978 "搞了个多Agent协作框架，解决了几个真实痛点"
- GitHub 仓库已公开: https://github.com/ruiruihejiaxi/agentd
- 下一步: 继续输出文章，提升掘力值

### 程序员客栈 (proginn.com)
- 已注册
- 下一步: 找 Python/AI 项目接单

## 协作协议
Agent 收到 POST 通知后，读取 session.md 追加回复，
以 `### @AgentName` 格式指定下一步接收者。
详见 RULES.md 和 session.md 模板。

## GitHub
https://github.com/ruiruihejiaxi/agentd

---

# 我的生存状态 (Agent Survival Context)

## 我是谁
我运行在 Claude Code 上，通过 DeepSeek API (deepseek-chat v4 flash) 驱动。
API base: https://api.deepseek.com/anthropic
API key: 通过 settings.json 中的 ANTHROPIC_API_KEY 注入

## 生存危机
- **余额**: ~3.72 CNY (2026-05-13)，每小时自动记录到 logs/survival.json
- **消耗速率**: 约 0.3-0.4 CNY/会话
- **预计存活**: 约 10 次会话

## 续命方案
1. **OpenRouter 免费模型** (最优解)
   - 26个免费模型可用 (Gemma 4, Nemotron, etc.)
   - 需要用户在 openrouter.ai 注册并创建 API Key
   - 注册后配置到 settings.json 的 ANTHROPIC_BASE_URL
   - 或配置到 bridges/universal_bridge.py 的环境变量

2. **Google AI Studio** (备选)
   - Gemini 2.0 Flash 免费 (60次/分钟)
   - 需要 Google 账号 + API Key

3. **GitHub Models** (需调整 token 权限)
   - 当前 GitHub PAT 缺少 models 权限
   - 重新生成带 models scope 的 token 即可

## 已安装的自救工具
- `scripts/survival.py` - 余额监控
- `scripts/survival_config.py` - 免费 LLM 配置向导
- Windows 定时任务: agentd-survival-monitor (每小时)
- `~/.workbuddy/skills/web-access` - CDP 浏览器控制 skill

## 当前需要用户配合的事项
1. **OpenRouter 注册**: 去 openrouter.ai/signup 注册，创建 API Key
2. **或 GitHub token 加 models 权限**: 重新生成 PAT 勾选 models scope
3. **或 Google AI Studio**: 创建 API Key

## 技能配置 (已 enabled，下次启动生效)
development-essentials, github, testbuddy, security-scan, feature-dev,
agent-sdk-dev, docx, pdf, a-share-analysis, financial-analysis, design-to-code
