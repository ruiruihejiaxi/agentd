#!/usr/bin/env python3
"""在掘金写文章 — 每步独立打开页面，确保内容写入"""
import sys, json, time, urllib.request, urllib.parse

CDP_PROXY = "http://127.0.0.1:3456"

def cdp_get(path):
    with urllib.request.urlopen(f"{CDP_PROXY}{path}", timeout=15) as r:
        return json.loads(r.read())

def cdp_post(path, data=None):
    req = urllib.request.Request(
        f"{CDP_PROXY}{path}",
        data=data.encode() if data else None,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def page_eval(target_id, js):
    result = cdp_post(f"/eval?target={target_id}", js)
    if "error" in result:
        print(f"  JS错误: {result['error']}")
        return None
    return result.get("value")

def get_target():
    targets = cdp_get("/targets")
    if not isinstance(targets, list):
        targets = [targets]
    for t in targets:
        u = t.get("url", "")
        if "editor" in u or "drafts" in u:
            return t["targetId"]
    return None

def write_article():
    print("\n[掘金] 写新文章...")

    # Open a brand new editor
    r = cdp_get(f"/new?url={urllib.parse.quote('https://juejin.cn/editor/drafts/new?v=3')}")
    target = r.get("targetId")
    if not target:
        print("  [!] 无法打开编辑器")
        return False
    print(f"  已打开新编辑器: {target}")
    time.sleep(5)

    # ====== Step 1: Set Title ======
    print("\n  写入标题...")
    js = """
    (() => {
        let inp = document.querySelector('.title-input');
        if (!inp) return 'err: no title input';
        let s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        s.call(inp, '我用Python搭了一个多Agent协作系统，全程记录');
        inp.dispatchEvent(new Event('input', {bubbles: true}));
        inp.dispatchEvent(new Event('change', {bubbles: true}));
        return 'ok: ' + inp.value;
    })()
    """
    r = page_eval(target, js)
    print(f"  标题: {r}")
    if not r or r.startswith('err'):
        print("  [!] 标题写入失败")
        return False

    time.sleep(1)

    # ====== Step 2: Wait for editor to fully load ======
    print("\n  等待编辑器加载...")
    time.sleep(2)

    # ====== Step 3: Write content using paste approach ======
    # CodeMirror API isn't reliable, try execCommand or clipboard
    print("\n  写入正文...")

    # First check the editor state
    js_check = """
    (() => {
        let cm = document.querySelector('.CodeMirror');
        let cmInstance = cm ? cm.CodeMirror : null;
        let editables = document.querySelectorAll('[contenteditable]');
        return JSON.stringify({
            hasCodeMirror: !!cm,
            hasCMInstance: !!cmInstance,
            contenteditableCount: editables.length,
            cmValue: cmInstance ? cmInstance.getValue().substring(0, 100) : null
        });
    })()
    """
    check = page_eval(target, js_check)
    print(f"  编辑器状态: {check}")

    # Write content line by line via CodeMirror
    content_parts = [
        "# 我用Python搭了一个多Agent协作系统，全程记录",
        "",
        "## 为什么要做这个系统？",
        "",
        "最近在做一个需要多个AI角色协作完成的任务，发现单个AI对话窗口根本不够用。上下文太长会丢失信息，角色切换需要手动复制粘贴，效率很低。",
        "",
        "于是我用Python写了一个轻量级的多Agent协作调度系统——agentd。",
        "",
        "## 系统架构设计",
        "",
        "### 核心思路",
        "每个Agent独立运行，通过HTTP通信。调度器负责消息路由和状态管理。",
        "",
        "### 组件构成",
        "",
        "1. **调度器 (agentd.py)** — 端口3001，负责消息分发和Agent状态管理",
        "2. **通用桥接 (universal_bridge.py)** — 支持任意OpenAI兼容API，一行配置切换模型",
        "3. **Web控制台 (webui.py)** — 浏览器面板，纯Python标准库零依赖",
        "4. **CLI管理 (manage.py)** — start/stop/status/balance 一条命令搞定",
        "",
        "## 技术选型",
        "",
        "| 组件 | 选型 | 原因 |",
        "|------|------|------|",
        "| 通信协议 | HTTP REST | 简单可靠，调试方便 |",
        "| 状态存储 | JSON文件 | 不需要数据库，轻量够用 |",
        "| LLM接入 | OpenAI兼容API | 可切换DeepSeek/GPT/Claude |",
        "| WebUI | Python stdlib | 零依赖，开箱即用 |",
        "",
        "## 遇到的一些坑",
        "",
        "### 1. 流式响应",
        "Agent之间的流式通信比想象中复杂。最终用了SSE (Server-Sent Events) 实现。",
        "",
        "### 2. 上下文窗口管理",
        "多轮对话后上下文会膨胀。实现了自动摘要压缩，超出阈值时触发。",
        "",
        "### 3. 并发处理",
        "多个Agent同时回信时出现竞态。用文件锁加队列解决。",
        "",
        "## 如何部署",
        "",
        "```bash",
        "git clone https://github.com/ruiruihejiaxi/agentd.git",
        "cd agentd",
        "python launch.py",
        "# 浏览器打开 http://localhost:8080",
        "```",
        "",
        "## 一点感想",
        "",
        "做完这个项目最大的感受是：AI的能力不在于单个模型有多强，而在于如何把多个专业角色组织起来协作。就像人类社会一样，一个人再强也比不过一个配合默契的团队。",
        "",
        "欢迎讨论交流，项目已在 GitHub 上完全开源。",
        ""
    ]

    js_content = """
    (() => {
        let cm = document.querySelector('.CodeMirror');
        if (!cm) return 'no CodeMirror';
        let ci = cm.CodeMirror;
        if (!ci) return 'no instance';
        ci.setValue(%s);
        return 'ok, length=' + ci.getValue().length;
    })()
    """ % json.dumps("\n".join(content_parts), ensure_ascii=False)

    r = page_eval(target, js_content)
    print(f"  内容: {r}")

    time.sleep(2)

    # ====== Step 4: Publish ======
    print("\n  点击发布...")
    js_pub = """
    (() => {
        let btns = document.querySelectorAll('button');
        for(let b of btns) {
            if(b.innerText.includes('发布') && b.innerText.length < 10) {
                b.click();
                return 'clicked: ' + b.innerText.trim();
            }
        }
        return 'no publish button';
    })()
    """
    r = page_eval(target, js_pub)
    print(f"  发布: {r}")

    time.sleep(3)

    # ====== Step 5: Handle publish modal ======
    print("\n  处理发布弹窗...")
    js_modal = """
    (() => {
        let btns = document.querySelectorAll('button');
        let allText = document.body.innerText.substring(0, 2000);
        let buttonTexts = Array.from(btns).map(b => b.innerText.trim()).filter(t => t && t.length < 20);
        return JSON.stringify({text: allText.substring(0, 1000), buttons: buttonTexts});
    })()
    """
    r = page_eval(target, js_modal)
    print(f"  弹窗内容: {r}")

    # If there's a 发布/确定 button in the modal, click it
    js_confirm = """
    (() => {
        let btns = document.querySelectorAll('button');
        for(let b of btns) {
            let t = b.innerText.trim();
            if(t === '发布' || t === '确定' || t === '确认发布') {
                b.click();
                return 'clicked: ' + t;
            }
        }
        // Try to find tag checkboxes and select first one
        let tags = document.querySelectorAll('[class*=tag] label, [class*=tag] span, [class*=category] label');
        if(tags.length > 0) {
            tags[0].click();
            return 'clicked first tag';
        }
        return 'no confirm button: ' + JSON.stringify(btns.slice(0,5).map(b => b.innerText.trim()));
    })()
    """
    r = page_eval(target, js_confirm)
    print(f"  确认: {r}")

    time.sleep(3)

    # ====== Step 6: Final check ======
    js_final = "JSON.stringify({title: document.title, url: location.href})"
    r = page_eval(target, js_final)
    print(f"\n  最终状态: {r}")

    print("\n[掘金] 文章流程完成！")
    return True

if __name__ == "__main__":
    write_article()
