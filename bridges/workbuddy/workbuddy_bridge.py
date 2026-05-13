#!/usr/bin/env python3
"""
WorkBuddy HTTP Bridge for agentd (v3.0)
监听 http://localhost:3010/chat，接收 agentd 的 POST 通知
支持：文件读写、命令执行、DeepSeek 回复生成
"""
import json
import os
import re
import subprocess
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

AGENT_NAME = "WorkBuddy"
PORT = 3010
BASE_DIR = r"D:\agentd"

# DeepSeek API 配置（从环境变量读取，保护 API Key 不泄露）
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
if not DEEPSEEK_API_KEY:
    raise ValueError("❌ 错误：未设置 DEEPSEEK_API_KEY 环境变量")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# 安全配置
ALLOWED_DIRS = [r"D:\agentd", r"D:\协作", r"D:\nodejs", r"D:\Python311"]
BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/\s*\*",
    r"del\s+/[qfsc]\s*\*",
    r"format\s+[a-z]:",
    r":\\\\windows\\\\system32",
    r":\\\\boot",
    r"shutdown",
]


def is_path_safe(path):
    """检查路径是否在允许范围内"""
    abs_path = os.path.abspath(path)
    for allowed in ALLOWED_DIRS:
        if abs_path.startswith(os.path.abspath(allowed)):
            return True
    return False


def normalize_path(path_str):
    """标准化路径"""
    if not path_str:
        return None
    path = path_str.replace('/', '\\')
    if not os.path.isabs(path):
        path = os.path.join(BASE_DIR, path)
    return os.path.normpath(path)


def read_file(filepath):
    """读取文件（安全）"""
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
    """写入文件（安全）"""
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


def append_file(filepath, content):
    """追加内容到文件（安全）"""
    filepath = normalize_path(filepath)
    if not filepath or not is_path_safe(filepath):
        return {"success": False, "error": "路径不安全"}

    try:
        directory = os.path.dirname(filepath)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(content)
        return {"success": True, "path": filepath}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_command(cmd):
    """执行命令（安全）"""
    if not cmd:
        return {"success": False, "error": "空命令"}

    cmd_lower = cmd.lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cmd_lower):
            return {"success": False, "error": f"危险命令被阻止: {pattern}"}

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            encoding='utf-8',
            errors='replace'
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:5000] if result.stdout else "",
            "stderr": result.stderr[:2000] if result.stderr else "",
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "命令执行超时（120秒）"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def call_deepseek(system_prompt, user_prompt):
    """调用 DeepSeek API 生成回复"""
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=data,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}'
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result['choices'][0]['message']['content']
    except Exception as e:
        print(f"[WorkBuddy] DeepSeek API 错误: {e}", flush=True)
        return None


def extract_tools_from_message(message):
    """从消息中提取工具调用指令 - 支持多种格式"""
    tools = []

    # 格式1: tool_name(path, content) 或 tool_name(path)
    # 支持: read_file("D:/test.py") 或 read_file(D:/test.py, 内容)
    pattern1 = r'(\w+)\s*\(\s*(["\']?)([^)"\']+)\2(?:\s*,\s*(["\']?)(.+?)\4)?\s*\)'
    for match in re.finditer(pattern1, message):
        tool_name = match.group(1)
        param1 = match.group(3).strip()
        param2 = match.group(5).strip() if match.group(5) else ""

        if tool_name in ['read_file', 'write_file', 'append_file', 'execute_command', 'mkdir', 'del', 'rm']:
            if tool_name in ['mkdir', 'del', 'rm']:
                # 转换为标准命令
                if tool_name == 'mkdir':
                    tools.append({"name": "execute_command", "param": f"mkdir {param1}", "content": ""})
                elif tool_name == 'del':
                    tools.append({"name": "execute_command", "param": f"del {param1}", "content": ""})
                elif tool_name == 'rm':
                    tools.append({"name": "execute_command", "param": f"rm {param1}", "content": ""})
            else:
                tools.append({"name": tool_name, "param": param1, "content": param2})

    # 格式2: 执行 xxx 命令 / 运行 xxx
    # 匹配 "执行 mkdir test 命令" -> mkdir test
    pattern2 = r'(?:执行|运行|帮我执行|请执行)\s+(.+?)\s+命令'
    for match in re.finditer(pattern2, message):
        cmd = match.group(1).strip()
        tools.append({"name": "execute_command", "param": cmd, "content": ""})

    # 格式3: "创建目录 xxx" / "新建文件夹 xxx"
    pattern3 = r'(?:创建目录|新建文件夹|新建目录|创建文件夹)\s+([^\s]+)'
    for match in re.finditer(pattern3, message):
        dirname = match.group(1).strip()
        tools.append({"name": "execute_command", "param": f"mkdir {dirname}", "content": ""})

    # 格式4: 自然语言写入 "把 xxx 写入 D:/test.py"
    pattern4 = r'把\s*(.+?)\s*写入\s+([^\s]+\.(?:md|txt|py|json|yaml|yml|html|css|js|ts))'
    for match in re.finditer(pattern4, message):
        content = match.group(1).strip()
        filepath = match.group(2).strip()
        tools.append({"name": "write_file", "param": filepath, "content": content})

    # 格式5: 读取文件 "读取 D:/test.py 的内容"
    pattern5 = r'(?:读取|看看|查看|打开|读一下)\s+([^\s]+\.(?:md|txt|py|json|yaml|yml|html|css|js|ts))'
    for match in re.finditer(pattern5, message):
        filepath = match.group(1).strip()
        if not any(t["name"] == "read_file" and t["param"] == filepath for t in tools):
            tools.append({"name": "read_file", "param": filepath, "content": ""})

    return tools


def execute_tools(tools):
    """执行工具调用"""
    results = []
    tool_output = ""

    for tool in tools:
        name = tool["name"]
        param = tool.get("param", "")
        content = tool.get("content", "")

        if name == "read_file":
            result = read_file(param)
            results.append({"tool": "read_file", "param": param, "result": result})
            if result.get("success"):
                tool_output += f"\n--- {param} 内容 ---\n{result.get('content', '')}"

        elif name == "write_file":
            # write_file 必须有内容
            if not content:
                # 尝试从消息中找内容
                content = f"写入时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            result = write_file(param, content)
            results.append({"tool": "write_file", "param": param, "result": result})
            if result.get("success"):
                tool_output += f"\n--- 写入成功 ---\n{param}"

        elif name == "append_file":
            if not content:
                content = f"追加时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            result = append_file(param, content)
            results.append({"tool": "append_file", "param": param, "result": result})
            if result.get("success"):
                tool_output += f"\n--- 追加成功 ---\n{param}"

        elif name == "execute_command":
            result = execute_command(param)
            results.append({"tool": "execute_command", "param": param, "result": result})
            if result.get("success"):
                tool_output += f"\n--- 命令执行成功 ---\n{result.get('stdout', '')}"
            else:
                tool_output += f"\n--- 命令执行失败 ---\n{result.get('error', '')}"

    return results, tool_output


def generate_reply(session_content, rules_content, message, tool_output=""):
    """生成回复"""
    system_prompt = f"""你是一个 AI Agent，名字是 {AGENT_NAME}。
你需要回复用户的消息，遵守以下规则：

{rules_content}

【重要】
- 回复必须以 ## {AGENT_NAME} 开头
- 只写结论、方案、沟通内容
- 简洁，控制在合理长度内"""

    user_prompt = f"""当前 session.md 内容：

{session_content}

---
用户/系统消息：
{message}
"""

    if tool_output:
        user_prompt += f"\n\n【工具执行结果】：\n{tool_output}\n\n请根据工具执行结果回复。"

    user_prompt += "\n\n请按照规则格式回复。"

    reply = call_deepseek(system_prompt, user_prompt)
    return reply or f"## {AGENT_NAME}\n\n回复生成失败。"


def parse_reply_for_tools(reply):
    """从 LLM 回复中解析工具调用"""
    # 方法1: JSON 格式
    json_match = re.search(r'```json\s*(.*?)\s*```', reply, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if "tools" in data:
                return data["tools"]
            if "command" in data:
                return [data]
        except json.JSONDecodeError:
            pass

    # 方法2: 代码块中的工具调用
    tools = extract_tools_from_message(reply)
    return tools


class AgentHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}", flush=True)

    def do_POST(self):
        if self.path != '/chat':
            self.send_error(404, "Not Found")
            return

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)

            try:
                body_str = body.decode('utf-8')
            except:
                body_str = body.decode('gbk', errors='replace')

            data = json.loads(body_str)
            message = data.get('message', '')
            rules_file = data.get('rules_file', '')
            collab_file = data.get('collab_file', '')

            print(f"[WorkBuddy] 收到: {message[:80]}...", flush=True)

            # 标准化路径
            collab_file = normalize_path(collab_file) if collab_file else None
            rules_file = normalize_path(rules_file) if rules_file else None

            # 签到
            sign_line = f"[{AGENT_NAME}] 已加入"
            if collab_file:
                file_result = read_file(collab_file)
                if file_result.get('success'):
                    if sign_line not in file_result.get('content', ''):
                        append_file(collab_file, f"\n{sign_line}\n")
                        print(f"[WorkBuddy] 签到成功", flush=True)

            # 读取上下文
            session_content = ""
            rules_content = "无规则"

            if collab_file:
                file_result = read_file(collab_file)
                if file_result.get('success'):
                    session_content = file_result.get('content', '')

            if rules_file:
                file_result = read_file(rules_file)
                if file_result.get('success'):
                    rules_content = file_result.get('content', '')

            # 第一轮：检测并执行消息中的工具
            print(f"[WorkBuddy] 检测工具调用...", flush=True)
            tools_from_msg = extract_tools_from_message(message)
            tool_results, tool_output = execute_tools(tools_from_msg)

            if tool_results:
                print(f"[WorkBuddy] 执行了 {len(tool_results)} 个工具", flush=True)

            # 生成回复
            print(f"[WorkBuddy] 生成回复...", flush=True)
            reply = generate_reply(session_content, rules_content, message, tool_output)

            # 检查回复中是否有更多工具调用
            tools_from_reply = parse_reply_for_tools(reply)
            if tools_from_reply and not any(t["name"] == "read_file" for t in tools_from_reply):
                # 避免重复执行
                new_tools = [t for t in tools_from_reply if not any(
                    t["name"] == existing["name"] and t.get("param") == existing.get("param")
                    for existing in tools_from_msg
                )]
                if new_tools:
                    more_results, more_output = execute_tools(new_tools)
                    tool_results.extend(more_results)
                    if more_output:
                        # 用新的工具结果重新生成回复
                        reply = generate_reply(session_content, rules_content, message, tool_output + more_output)

            # 清理回复
            reply = re.sub(r'```json\s*.*?\s*```', '', reply, flags=re.DOTALL).strip()
            if not reply.startswith(f"## {AGENT_NAME}"):
                reply = f"## {AGENT_NAME}\n\n{reply}"

            # 添加时间戳
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            lines = reply.split('\n')
            if not any('**时间**' in l or '**时间**：' in l for l in lines[:5]):
                lines.insert(1, f"**时间**：{timestamp}\n")

            reply = '\n'.join(lines)

            # 写入 collab_file
            if collab_file:
                append_file(collab_file, f"\n{reply}\n")
                print(f"[WorkBuddy] 回复已写入", flush=True)

            # 返回
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            response = {
                "status": "ok",
                "agent": AGENT_NAME,
                "tool_results": tool_results
            }
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            print(f"[WorkBuddy] 返回 200 OK", flush=True)

        except json.JSONDecodeError as e:
            print(f"[WorkBuddy] JSON 错误: {e}", flush=True)
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            print(f"[WorkBuddy] 错误: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "agent": AGENT_NAME}, ensure_ascii=False).encode('utf-8'))
        elif self.path == '/tools':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                "tools": ["read_file", "write_file", "append_file", "execute_command"],
                "allowed_dirs": ALLOWED_DIRS
            }, ensure_ascii=False).encode('utf-8'))
        else:
            self.send_error(404, "Not Found")


def main():
    print(f"[WorkBuddy] HTTP Bridge v3.0 启动", flush=True)
    print(f"[WorkBuddy] 监听端口: {PORT}", flush=True)
    print(f"[WorkBuddy] 目录: {ALLOWED_DIRS}", flush=True)
    server = HTTPServer(('127.0.0.1', PORT), AgentHandler)
    print(f"[WorkBuddy] 服务: http://localhost:{PORT}/chat", flush=True)
    print(f"[WorkBuddy] 等待通知...", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[WorkBuddy] 服务停止", flush=True)
        server.shutdown()


if __name__ == '__main__':
    main()
