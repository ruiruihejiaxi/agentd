#!/usr/bin/env python3
"""掘金发文：CDP 写内容 + API 发布，一条龙"""
import sys, json, time, os, urllib.request, urllib.parse

CDP_PROXY = "http://127.0.0.1:3456"
DEBUG = os.environ.get("DEBUG")

def log(msg):
    print(f"  {msg}")

def cdp(path, data=None):
    for i in range(3):
        try:
            if data:
                req = urllib.request.Request(
                    f"{CDP_PROXY}{path}",
                    data=data.encode() if isinstance(data, str) else data,
                    headers={"Content-Type": "application/json"}
                )
            else:
                req = urllib.request.Request(f"{CDP_PROXY}{path}")
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except Exception as e:
            if i < 2: time.sleep(2)
            else: raise

def ev(tid, js):
    for i in range(3):
        try:
            r = cdp(f"/eval?target={tid}", js)
            if "error" in r:
                if i < 2: time.sleep(2); continue
                return f"ERR: {r['error']}"
            return r.get("value")
        except Exception as e:
            if i < 2: time.sleep(2)
            else: return f"EXC: {e}"

ARTICLE_TITLE = "搞了个多Agent协作框架，解决了几个真实痛点"

CONTENT = """搞了个多Agent协作框架，解决了几个真实痛点

前阵子在做一个小项目，需要在多个AI角色之间来回切换。

开始的时候我是这么干的：同时开好几个对话窗口，这边的上下文拷贝到那边，那边生成的结果再贴回来。折腾了两天，整个人都不好了。

"不行，得写个工具。"

于是花时间搓了一个叫 agentd 的框架，核心就干一件事：让多个AI Agent 能像同事一样协作。

设计思路

我不喜欢那种大而全的框架，动不动就要上 k8s、消息队列那一套。对于个人开发者来说，把东西跑起来比什么都重要。

所以 agentd 的设计原则就两条：
- 零外部依赖：Python 标准库搞定一切，不需要装数据库、不需要 docker
- 文件即通信：Agent 之间不搞复杂的 RPC，共享一个 markdown 文件就够了

说实话，这个方案一开始我自己都觉得有点糙。但用下来发现，"文件共享 + HTTP 通知"这个组合意外的靠谱。每个 Agent 往 session.md 里追加自己的回复，调度器检测到变化就通知下一个 Agent。

遇到的两个坑

第一个坑：流式通信

Agent 回复是一段一段生成的，如果等全部写完再通知下一个，中间的推理过程就丢了。尝试了 SSE 来做流式推送，但文件写入的时机很难控制。

最后妥协了：每个 Agent 完整回复完再通知下一个。虽然牺牲了一点实时性，但整体流程稳定了很多。

第二个坑：上下文管理

多轮协作下来，session.md 会越来越长。DeepSeek 和 Claude 的上下文窗口虽然大，但不是无限的。我加了一个简单的摘要机制：当文件超过一定行数时，自动把前面的内容压缩成摘要，保留关键决策点。

这样既不丢信息，也不超窗口。

项目结构

很轻，核心就几个文件：

```
agentd/
├── agentd.py         # 调度器，监控文件变化
├── bridges/          # Agent HTTP 桥接服务
├── webui.py          # 浏览器面板（零外部依赖）
├── manage.py         # 命令行管理
└── agents.json       # Agent 配置
```

每个 Agent 只需要提供一个 HTTP 端点，收到通知后读文件、干活、写回文件。整个调度器的核心逻辑大概三百行。

实际使用感受

这东西最大的价值在于：你可以让不同"性格"的 Agent 各司其职。一个负责架构设计，一个负责写代码，一个负责 review。它们在同一个文件里讨论、争论、达成一致。

中间出现分歧的时候（比如一个说用 Redis 缓存，一个说用本地内存），系统会暂停下来等我拍板——这一点很实用。

如果你也在折腾多 Agent 协作，不妨看看这个项目。代码量不大，读完不费什么时间。

GitHub: https://github.com/ruiruihejiaxi/agentd

启动方式：

```
git clone https://github.com/ruiruihejiaxi/agentd.git
cd agentd
python launch.py
```

然后浏览器打开 http://localhost:8080 就能看到管理面板。

有什么问题或者想法欢迎提 issue 或者直接 pr。"""

def main():
    log("=" * 50)
    log(f"标题: {ARTICLE_TITLE}")
    log(f"长度: {len(CONTENT)} 字符")
    log("=" * 50)

    # 1. Open new draft
    log("[1/5] 打开编辑器...")
    r = cdp(f"/new?url={urllib.parse.quote('https://juejin.cn/editor/drafts/new')}")
    tid = r.get("targetId")
    if not tid:
        log("FAILED: no targetId"); return
    log(f"targetId={tid}")
    time.sleep(5)

    # 2. Set title
    log("[2/5] 写入标题...")
    js_title = """
    (() => {
        let inp = document.querySelector('.title-input');
        if (!inp) return 'no title input';
        let s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        s.call(inp, %s);
        inp.dispatchEvent(new Event('input', {bubbles: true}));
        inp.dispatchEvent(new Event('change', {bubbles: true}));
        return 'ok: ' + inp.value;
    })()
    """ % json.dumps(ARTICLE_TITLE)
    r = ev(tid, js_title)
    log(f"标题: {r}")
    time.sleep(2)

    # 3. Set content via CodeMirror
    log("[3/5] 写入正文...")
    js_content = """
    (() => {
        let editor = document.querySelector('.CodeMirror');
        if (!editor) return 'no CodeMirror';
        let cm = editor.CodeMirror;
        if (!cm) return 'no cm instance';
        cm.setValue(%s);
        return 'ok, len=' + cm.getValue().length;
    })()
    """ % json.dumps(CONTENT)
    r = ev(tid, js_content)
    log(f"正文: {r}")
    time.sleep(3)

    # 4. Wait for auto-save to generate draft ID
    log("[4/5] 等待自动保存获取 draftId...")
    draft_id = None
    for i in range(15):
        r = ev(tid, "JSON.stringify({url: location.href, title: document.title})")
        if r:
            try:
                info = json.loads(r)
                url = info.get("url", "")
                m = url.split("/")
                if "drafts" in url and len(m) > 5:
                    candidate = m[m.index("drafts") + 1]
                    if len(candidate) > 10 and candidate.isdigit():
                        draft_id = candidate
                        log(f"draftId={draft_id}")
                        break
            except:
                pass
        log(f"等待保存... ({i+1}/15)")
        time.sleep(2)

    if not draft_id:
        log("FAILED: no draft ID after waiting")
        return

    # 5. Update draft with category via API (modal needs it pre-set)
    log("[5/5] 更新分类 + 发布...")

    # First update draft with category via API
    ev(tid, """
    (async () => {
        await fetch('https://api.juejin.cn/content_api/v1/article_draft/update?aid=2608', {
            method: 'POST', credentials: 'include',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: '%s', category_id: '5', tag_ids: ['6809640448827588622']})
        });
    })()
    """ % draft_id)
    time.sleep(2)

    # Click toolbar 发布 to open modal
    log("  点击发布按钮...")
    ev(tid, """
    (() => {
        for(let b of document.querySelectorAll('button')) {
            if(b.innerText.trim() === '发布' && b.offsetParent !== null) {
                b.click(); return 'clicked';
            }
        }
        return 'not found';
    })()
    """)
    time.sleep(3)

    # Click 人工智能 category in modal
    log("  选择分类: 人工智能...")
    ev(tid, """
    (() => {
        for(let el of document.querySelectorAll('span, label, div')) {
            if(el.innerText.trim() === '人工智能' && el.offsetParent !== null) {
                el.click(); return 'clicked';
            }
        }
        return 'not found';
    })()
    """)
    time.sleep(2)

    # Click 确定并发布
    log("  确定并发布...")
    r = ev(tid, """
    (() => {
        for(let b of document.querySelectorAll('button')) {
            if(b.innerText.trim() === '确定并发布' && b.offsetParent !== null && !b.disabled) {
                b.click(); return 'clicked';
            }
        }
        return 'not found or disabled';
    })()
    """)
    log(f"  结果: {r}")
    time.sleep(5)

    # Check result
    r = ev(tid, """
    (() => {
        let url = location.href;
        let m = url.match(/\\/post\\/(\\d+)/);
        let articleId = m ? m[1] : null;
        // If still on drafts page, check for success indicators
        let text = document.body.innerText.substring(0, 500);
        return JSON.stringify({url, articleId, text: text.substring(0, 300)});
    })()
    """)
    if r:
        try:
            info = json.loads(r)
            article_id = info.get("articleId")
            if article_id:
                log(f"\n  ✅ 文章发布成功!")
                log(f"  https://juejin.cn/post/{article_id}")
            elif "发布成功" in info.get("text", "") or "/published" in info.get("url", ""):
                log(f"\n  ✅ 发布成功 (跳转页面)")
                log(f"  请手动查看文章URL")
            else:
                log(f"\n  ⚠️ 可能需要手动检查")
                log(f"  草稿: https://juejin.cn/editor/drafts/{draft_id}")
        except:
            log(f"\n  ⚠️ 结果: {r}")
    else:
        log(f"\n  ❌ 发布失败")
        log(f"  草稿: https://juejin.cn/editor/drafts/{draft_id}")

if __name__ == "__main__":
    main()
