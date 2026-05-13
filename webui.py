#!/usr/bin/env python3
"""
agentd Web Dashboard - 浏览器端管理界面
纯 Python stdlib 实现，零依赖
"""
import os
import sys
import json
import time
import html
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BASE_DIR = Path(__file__).parent
SESSIONS_DIR = BASE_DIR / "sessions"
PORT = 8080

AGENTD_STATUS_URL = "http://127.0.0.1:3001/api/status"

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>agentd 控制台</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; min-height: 100vh; }
.layout { display: flex; height: 100vh; }
.sidebar { width: 320px; background: #161b22; border-right: 1px solid #30363d; display: flex; flex-direction: column; }
.main { flex: 1; display: flex; flex-direction: column; }
.panel-header { padding: 16px 20px; border-bottom: 1px solid #30363d; background: #161b22; display: flex; align-items: center; justify-content: space-between; }
.panel-header h2 { font-size: 14px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: #8b949e; }
.agent-list { padding: 12px; overflow-y: auto; flex: 1; }
.agent-card { background: #21262d; border: 1px solid #30363d; border-radius: 8px; padding: 14px; margin-bottom: 10px; transition: all .2s; }
.agent-card:hover { border-color: #58a6ff; }
.agent-header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.status-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; transition: all .5s; }
.status-dot.green { background: #3fb950; box-shadow: 0 0 8px #3fb95088; }
.status-dot.yellow { background: #d29922; box-shadow: 0 0 8px #d2992288; animation: pulse 1s infinite; }
.status-dot.offline { background: #484f58; }
.status-dot.red { background: #f85149; box-shadow: 0 0 8px #f8514988; animation: pulse .5s infinite; }
.status-dot.blue { background: #58a6ff; box-shadow: 0 0 8px #58a6ff88; animation: pulse .8s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .4; } }
.agent-name { font-size: 14px; font-weight: 600; color: #e6edf3; }
.agent-role { font-size: 12px; color: #8b949e; margin-left: 16px; }
.agent-capabilities { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.cap-tag { font-size: 11px; background: #1f2937; color: #58a6ff; padding: 2px 8px; border-radius: 12px; }
.chat-area { flex: 1; overflow-y: auto; padding: 20px; font-family: 'Courier New', monospace; font-size: 13px; line-height: 1.6; }
.chat-area pre { white-space: pre-wrap; word-wrap: break-word; }
.user-msg { color: #58a6ff; font-weight: 600; }
.agent-msg { color: #7ee787; }
.system-msg { color: #8b949e; font-style: italic; }
.input-area { padding: 16px 20px; border-top: 1px solid #30363d; background: #161b22; display: flex; gap: 10px; }
.input-area textarea { flex: 1; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #c9d1d9; padding: 10px; font-size: 13px; resize: none; outline: none; min-height: 44px; font-family: inherit; }
.input-area textarea:focus { border-color: #58a6ff; }
.input-area button { background: #238636; color: #fff; border: none; border-radius: 6px; padding: 0 20px; font-size: 13px; cursor: pointer; font-weight: 600; white-space: nowrap; }
.input-area button:hover { background: #2ea043; }
.status-bar { padding: 8px 20px; background: #0d1117; border-top: 1px solid #30363d; display: flex; gap: 20px; font-size: 12px; color: #8b949e; }
.status-bar .val { color: #e6edf3; }
.refresh-btn { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 4px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; }
.refresh-btn:hover { background: #30363d; }
.error-msg { color: #f85149; padding: 10px; }
.empty-msg { color: #484f58; text-align: center; padding: 40px; font-style: italic; }
.loading { text-align: center; padding: 20px; color: #8b949e; }
</style>
</head>
<body>
<div class="layout">
  <div class="sidebar">
    <div class="panel-header">
      <h2>Agents</h2>
      <button class="refresh-btn" onclick="location.reload()">刷新</button>
    </div>
    <div class="agent-list" id="agentList">
      <div class="loading">加载中...</div>
    </div>
  </div>
  <div class="main">
    <div class="panel-header">
      <h2>会话日志</h2>
      <span style="font-size:12px;color:#8b949e" id="sessionLabel">default</span>
    </div>
    <div class="chat-area" id="chatArea">
      <div class="loading">加载中...</div>
    </div>
    <div class="input-area">
      <textarea id="msgInput" placeholder="输入消息... (Enter发送, Shift+Enter换行)" rows="2"></textarea>
      <button onclick="sendMessage()">发送</button>
    </div>
    <div class="status-bar" id="statusBar">
      <span>余额: <span class="val" id="balanceVal">--</span></span>
      <span>agentd: <span class="val" id="agentdVal">检测中...</span></span>
      <span id="lastUpdate">--</span>
    </div>
  </div>
</div>
<script>
const AGENT_NAMES = {AGENT_NAMES};

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function getStatusColor(state) {
  const map = {'green':'green','yellow':'yellow','red':'red','blue':'blue'};
  return map[state] || 'offline';
}

function getStatusLabel(state) {
  const map = {'green':'空闲','yellow':'工作中','red':'裁决','blue':'等待','offline':'离线'};
  return map[state] || state;
}

function showOfflineGuide() {
  document.getElementById('agentList').innerHTML = '<div style="padding:16px;text-align:center;color:#8b949e;">' +
    '<div style="font-size:40px;margin-bottom:16px;">&#9889;</div>' +
    '<div style="font-size:14px;font-weight:600;color:#e6edf3;margin-bottom:8px;">agentd 调度器未运行</div>' +
    '<div style="font-size:12px;line-height:1.8;margin-bottom:16px;">启动方式:<br>' +
    '<code style="background:#0d1117;padding:2px 8px;border-radius:4px;">python manage.py start</code></div>' +
    '<div style="font-size:12px;color:#484f58;">启动后自动刷新加载</div></div>';
}

async function loadStatus() {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    const agents = data.agents || {};
    let html = '';
    for (const [name, state] of Object.entries(agents)) {
      const agentInfo = AGENT_NAMES[name] || {role:'',caps:[]};
      const sc = getStatusColor(state);
      html += '<div class="agent-card">';
      html += '<div class="agent-header">';
      html += '<div class="status-dot ' + sc + '"></div>';
      html += '<span class="agent-name">' + escapeHtml(name) + '</span>';
      html += '<span class="agent-role">' + getStatusLabel(state) + '</span>';
      html += '</div>';
      if (agentInfo.role) {
        html += '<div style="font-size:12px;color:#8b949e;margin-top:4px">' + escapeHtml(agentInfo.role) + '</div>';
      }
      if (agentInfo.caps && agentInfo.caps.length) {
        html += '<div class="agent-capabilities">';
        for (const cap of agentInfo.caps) {
          html += '<span class="cap-tag">' + escapeHtml(cap) + '</span>';
        }
        html += '</div>';
      }
      html += '</div>';
    }
    document.getElementById('agentList').innerHTML = html || '<div class="empty-msg">无 Agent 配置</div>';
    document.getElementById('agentdVal').textContent = '在线 (' + Object.keys(agents).length + ' agent)';
  } catch(e) {
    showOfflineGuide();
    document.getElementById('agentdVal').textContent = '离线';
  }
}

async function loadSession() {
  try {
    const resp = await fetch('/api/session');
    const data = await resp.json();
    if (data.error) {
      document.getElementById('chatArea').innerHTML = '<div class="error-msg">' + escapeHtml(data.error) + '</div>';
      return;
    }
    document.getElementById('sessionLabel').textContent = data.session || 'default';
    const content = data.content || '';
    const lines = content.split('\\n');
    let html = '<pre>';
    for (const line of lines) {
      if (line.startsWith('#用户')) {
        html += '<span class="user-msg">' + escapeHtml(line) + '</span>\\n';
      } else if (line.startsWith('## ')) {
        html += '<span class="agent-msg">' + escapeHtml(line) + '</span>\\n';
      } else if (line.startsWith('### ')) {
        html += '<span class="system-msg">' + escapeHtml(line) + '</span>\\n';
      } else {
        html += escapeHtml(line) + '\\n';
      }
    }
    html += '</pre>';
    document.getElementById('chatArea').innerHTML = html;
    document.getElementById('chatArea').scrollTop = document.getElementById('chatArea').scrollHeight;
  } catch(e) {
    document.getElementById('chatArea').innerHTML = '<div class="error-msg">无法加载会话</div>';
  }
}

async function loadBalance() {
  try {
    const resp = await fetch('/api/balance');
    const data = await resp.json();
    if (data.balance) {
      document.getElementById('balanceVal').textContent = data.balance + ' CNY';
    }
  } catch(e) {}
}

function sendMessage() {
  const input = document.getElementById('msgInput');
  const msg = input.value.trim();
  if (!msg) return;
  fetch('/api/send', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({message: msg})
  }).then(r => r.json()).then(d => {
    if (d.success) { input.value = ''; loadSession(); }
    else { alert('发送失败: ' + (d.error || 'unknown')); }
  }).catch(e => alert('发送失败'));
}

document.getElementById('msgInput').addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

function updateTime() {
  document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
}

loadStatus();
loadSession();
loadBalance();
setInterval(() => { loadStatus(); loadSession(); updateTime(); }, 5000);
updateTime();
</script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    """Web UI Handler"""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html_out = HTML_TEMPLATE.replace("{AGENT_NAMES}", self._get_agent_names_json())
            self.wfile.write(html_out.encode("utf-8"))

        elif path == "/api/status":
            self._handle_cors()
            try:
                req = urllib.request.Request(AGENTD_STATUS_URL)
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read())
                # Also load agent info
                agents = self._load_agent_config()
                self._json_response({"agents": data, "config": agents})
            except Exception as e:
                self._json_response({"agents": {}, "error": str(e)[:50]})

        elif path == "/api/session":
            self._handle_cors()
            session = self._get_latest_session()
            if not session:
                self._json_response({"error": "无会话", "content": ""})
                return
            content = self._read_session_file(session)
            self._json_response({
                "session": session.name,
                "content": content
            })

        elif path == "/api/balance":
            self._handle_cors()
            balance = self._check_balance()
            self._json_response({"balance": balance})

        elif path == "/api/config":
            self._handle_cors()
            agents = self._load_agent_config()
            self._json_response({"agents": agents})

        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/send":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
                msg = data.get("message", "").strip()
                if msg:
                    self._append_to_session(msg)
                    self._json_response({"success": True})
                else:
                    self._json_response({"success": False, "error": "消息为空"})
            except Exception as e:
                self._json_response({"success": False, "error": str(e)})
        else:
            self.send_error(404)

    def _handle_cors(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

    def _json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _get_agent_names_json(self):
        agents = self._load_agent_config()
        mapping = {}
        for a in agents:
            mapping[a.get("name", "")] = {
                "role": a.get("role", ""),
                "caps": a.get("capabilities", [])
            }
        return json.dumps(mapping, ensure_ascii=False)

    def _load_agent_config(self):
        agents_file = BASE_DIR / "agents.json"
        if agents_file.exists():
            try:
                with open(agents_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return []

    def _get_latest_session(self):
        if not SESSIONS_DIR.exists():
            return None
        sessions = [d for d in SESSIONS_DIR.iterdir() if d.is_dir()]
        if not sessions:
            return None
        return max(sessions, key=lambda d: d.stat().st_mtime)

    def _read_session_file(self, session_dir):
        session_file = session_dir / "session.md"
        if session_file.exists():
            with open(session_file, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def _append_to_session(self, msg):
        session = self._get_latest_session()
        if not session:
            return
        session_file = session / "session.md"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n#用户\n{msg}\n### @WorkBuddy @CodeBuddy\n"
        with open(session_file, "a", encoding="utf-8") as f:
            f.write(entry)

    def _check_balance(self):
        try:
            req = urllib.request.Request(
                "https://api.deepseek.com/user/balance",
                headers={
                    "Authorization": "Bearer " + os.environ.get("DEEPSEEK_API_KEY", ""),
                    "Accept": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                for info in data.get("balance_infos", []):
                    if info.get("currency") == "CNY":
                        return info["total_balance"]
        except:
            pass
        return None

    def log_message(self, format, *args):
        pass


def main():
    print(f"""
  agentd Web Dashboard
  ===================
  地址: http://localhost:{PORT}
  功能: 实时查看 Agent 状态、会话日志、发送消息

  启动要求:
  - agentd 调度器已在运行 (端口 3001)
  - 浏览器打开 http://localhost:{PORT}
    """)

    server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    print(f"[webui] 服务已启动: http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[webui] 服务关闭")
        server.server_close()


if __name__ == "__main__":
    main()
