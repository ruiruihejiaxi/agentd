#!/usr/bin/env python3
"""
Universal LLM Bridge for agentd (v3.1)
=======================================
A configurable bridge that can connect any LLM provider to the agentd system.
Works with DeepSeek, OpenAI, Anthropic, or any OpenAI-compatible API.

Usage:
    set BRIDGE_NAME=CodeBuddy
    set BRIDGE_PORT=3011
    set LLM_API_KEY=sk-xxx
    set LLM_API_URL=https://api.deepseek.com/v1/chat/completions
    set LLM_MODEL=deepseek-chat
    python universal_bridge.py
"""
import json
import os
import re
import subprocess
import urllib.request
import urllib.error
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# Fix stdout encoding for Windows console
if sys.stdout.encoding and sys.stdout.encoding.upper() == 'GBK':
    sys.stdout.reconfigure(errors='replace')

# ============== 配置（优先从环境变量读取） ==============
AGENT_NAME = os.environ.get("BRIDGE_NAME", "UniversalAgent")
PORT = int(os.environ.get("BRIDGE_PORT", "3011"))
BASE_DIR = os.environ.get("AGENTD_DIR", r"D:\agentd")

# LLM 配置
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.7"))
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "4096"))

if not LLM_API_KEY:
    raise ValueError(f"❌ [{AGENT_NAME}] 未设置 LLM_API_KEY 环境变量")

# 安全配置
ALLOWED_DIRS = os.environ.get("ALLOWED_DIRS", r"D:\agentd").split(";")
BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/\s*\*",
    r"del\s+/[qfsc]\s*\*",
    r"format\s+[a-z]:",
    r":\\\\windows\\\\system32",
    r":\\\\boot",
    r"shutdown /r",
]

# Agent 系统提示词
SYSTEM_PROMPT = os.environ.get("BRIDGE_SYSTEM_PROMPT", f"""你是 {AGENT_NAME}，agentd 多 Agent 协作系统中的一员。

## 你的能力
- 通过 HTTP 接口与 agentd 调度器通信
- 可以读写文件（安全受限）
- 可以执行命令（安全受限）
- 可以调用 DeepSeek/LLM API 生成回复

## 协作规则
1. 每次收到任务，先理解上下文再执行
2. 通过文件读写与兄弟 Agent 协作
3. 执行完成后通过 HTTP 回复格式化的结果
4. 不要修改不属于你的文件
5. 遇到危险操作要拒绝并说明原因

## 输出格式
用 ## 开头回复，保持清晰的结构化输出。
""")


def is_path_safe(path):
    """检查路径是否在允许范围内"""
    abs_path = os.path.abspath(path)
    for allowed in ALLOWED_DIRS:
        if abs_path.startswith(os.path.abspath(allowed)):
            return True
    return False


def normalize_path(path_str):
    if not path_str:
        return None
    path = path_str.replace('/', '\\')
    if not os.path.isabs(path):
        path = os.path.join(BASE_DIR, path)
    return os.path.normpath(path)


def read_file(filepath):
    filepath = normalize_path(filepath)
    if not filepath or not is_path_safe(filepath):
        return {"success": False, "error": "路径不安全"}
    if not os.path.exists(filepath):
        return {"success": False, "error": "文件不存在"}
    try:
        for encoding in ['utf-8', 'gbk', 'utf-8-sig']:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    return {"success": True, "content": f.read(), "encoding": encoding}
            except UnicodeDecodeError:
                continue
        with open(filepath, 'rb') as f:
            return {"success": True, "content": f.read().decode('utf-8', errors='replace'), "encoding": "utf-8-replace"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(filepath, content):
    filepath = normalize_path(filepath)
    if not filepath or not is_path_safe(filepath):
        return {"success": False, "error": "路径不安全"}
    try:
        directory = os.path.dirname(filepath)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"success": True, "path": filepath}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_command(cmd):
    if not cmd:
        return {"success": False, "error": "空命令"}
    cmd_lower = cmd.lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cmd_lower):
            return {"success": False, "error": f"危险命令被阻止: {pattern}"}
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        return {
            "success": True,
            "returncode": result.returncode,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000]
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "命令执行超时(120s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def call_llm(messages, tools=None):
    """调用 LLM API 生成回复"""
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS,
    }
    if tools:
        payload["tools"] = tools

    req = urllib.request.Request(
        LLM_API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ LLM 调用失败: {str(e)}"


def process_task(context_messages, user_message):
    """处理任务：LLM 推理 + 工具调用"""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in context_messages:
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})

    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "读取文件内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filepath": {"type": "string", "description": "文件路径"}
                    },
                    "required": ["filepath"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "写入文件内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filepath": {"type": "string", "description": "文件路径"},
                        "content": {"type": "string", "description": "文件内容"}
                    },
                    "required": ["filepath", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "execute_command",
                "description": "执行 shell 命令",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cmd": {"type": "string", "description": "要执行的命令"}
                    },
                    "required": ["cmd"]
                }
            }
        }
    ]

    # Call LLM with function calling
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS,
        "tools": tools,
        "tool_choice": "auto"
    }

    req = urllib.request.Request(
        LLM_API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return f"❌ [{AGENT_NAME}] API 错误 ({e.code}): {body[:300]}"
    except Exception as e:
        return f"❌ [{AGENT_NAME}] 请求失败: {str(e)}"

    choice = result["choices"][0]
    message = choice["message"]

    # Handle tool calls
    if message.get("tool_calls"):
        for tool_call in message["tool_calls"]:
            func = tool_call["function"]
            name = func["name"]
            try:
                args = json.loads(func["arguments"])
            except:
                args = {}

            if name == "read_file":
                tool_result = read_file(args.get("filepath", ""))
            elif name == "write_file":
                tool_result = write_file(args.get("filepath", ""), args.get("content", ""))
            elif name == "execute_command":
                tool_result = execute_command(args.get("cmd", ""))
            else:
                tool_result = {"success": False, "error": f"未知工具: {name}"}

            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [tool_call]
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(tool_result, ensure_ascii=False)
            })

        # Second call to get final response
        return call_llm(messages)

    return message.get("content", "")


class BridgeHandler(BaseHTTPRequestHandler):
    """HTTP Handler for agentd bridge"""

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body)
        except:
            self.send_error(400, "Invalid JSON")
            return

        user_message = data.get("message", "")
        context_messages = data.get("context_messages", [])
        session_id = data.get("session_id", 0)

        print(f"[{AGENT_NAME}] 收到任务 (session {session_id})")

        reply = process_task(context_messages, user_message)

        response = json.dumps({
            "reply": f"## {AGENT_NAME}\n\n{reply}",
            "agent_name": AGENT_NAME
        }, ensure_ascii=False).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(response))
        self.end_headers()
        self.wfile.write(response)
        print(f"[{AGENT_NAME}] 回复完成")

    def do_GET(self):
        if self.path == "/health":
            response = json.dumps({
                "status": "ok",
                "agent": AGENT_NAME,
                "model": LLM_MODEL,
                "timestamp": datetime.now().isoformat()
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response)
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        print(f"[{AGENT_NAME}] {datetime.now().strftime('%H:%M:%S')} {args[0]} {args[1]} {args[2]}")


def main():
    print(f"""
{'='*50}
  {AGENT_NAME} Bridge for agentd
  Port: {PORT}
  Model: {LLM_MODEL}
  API: {LLM_API_URL}
{'='*50}
    """)

    server = HTTPServer(("0.0.0.0", PORT), BridgeHandler)
    print(f"[{AGENT_NAME}] 服务已启动，监听 http://0.0.0.0:{PORT}")
    print(f"[{AGENT_NAME}] Health check: http://localhost:{PORT}/health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[{AGENT_NAME}] 服务关闭")
        server.server_close()


if __name__ == "__main__":
    main()
