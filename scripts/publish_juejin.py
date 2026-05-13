#!/usr/bin/env python3
"""
掘金发布文章 — 打开草稿 → 选标签分类 → 发布
一次执行，避免 CDP 跨进程 target 过期
"""
import sys, json, time, urllib.request, urllib.parse

CDP_PROXY = "http://127.0.0.1:3456"

def cdp_get(path):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"{CDP_PROXY}{path}", timeout=20) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt < 2: time.sleep(2)
            else: raise

def cdp_post(path, data=None):
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f"{CDP_PROXY}{path}",
                data=data.encode() if data else None,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt < 2: time.sleep(2)
            else: raise

def pe(tid, js, label=""):
    """page_eval with retry and logging"""
    if label: print(f"  {label}...", end=" ", flush=True)
    for attempt in range(3):
        try:
            r = cdp_post(f"/eval?target={tid}", js)
            val = r.get("value") if "error" not in r else f"ERR: {r['error']}"
            if label: print(val)
            return val
        except Exception as e:
            if attempt < 2: time.sleep(2)
            else:
                if label: print(f"FAILED: {e}")
                return None

def main():
    print("\n" + "="*50)
    print("  掘金发布文章")
    print("="*50)

    draft_id = "7639094915608330280"
    draft_url = f"https://juejin.cn/editor/drafts/{draft_id}"

    # 1. Open the draft
    print(f"\n[1/7] 打开草稿...")
    r = cdp_get(f"/new?url={urllib.parse.quote(draft_url)}")
    tid = r.get("targetId")
    if not tid: print("  FAILED"); return
    print(f"  OK: {tid}")
    time.sleep(5)

    # 2. Check page loaded
    pe(tid, "document.title", "[2/7] 页面")

    # 3. Click 发布 in toolbar to open modal
    pe(tid, """
        (() => {
            for(let b of document.querySelectorAll('button')) {
                if(b.innerText.trim() === '发布' && b.offsetParent !== null) {
                    b.click(); return 'clicked';
                }
            }
            return 'not found';
        })()
    """, "[3/7] 点击发布按钮")
    time.sleep(3)

    # 4. Click 人工智能 category
    pe(tid, """
        (() => {
            for(let el of document.querySelectorAll('span, label, div')) {
                if(el.innerText.trim() === '人工智能' && el.offsetParent !== null) {
                    el.click(); return 'clicked 人工智能';
                }
            }
            return 'not found';
        })()
    """, "[4/7] 选择分类")
    time.sleep(1)

    # 5. Click tag search area to activate it, then click 后端 tag
    pe(tid, """
        (() => {
            // Find tag search area and click it
            for(let el of document.querySelectorAll('*')) {
                let t = el.innerText.trim();
                if(t === '请搜索添加标签' && el.offsetParent !== null) {
                    el.click();
                    setTimeout(() => {
                        // After clicking search area, find and click 后端 tag
                        for(let el2 of document.querySelectorAll('*')) {
                            if(el2.innerText.trim() === '后端' && el2.offsetParent !== null) {
                                el2.click();
                                break;
                            }
                        }
                    }, 500);
                    return 'activated tag search';
                }
            }
            return 'not found';
        })()
    """, "[5/7] 选标签")
    time.sleep(2)

    # Check tags visible now
    pe(tid, """
        (() => {
            let found = [];
            for(let el of document.querySelectorAll('*')) {
                let t = el.innerText.trim();
                if(el.offsetParent !== null && (t === '前端' || t === '后端' || t === 'Python' || t === 'JavaScript')) {
                    found.push(t);
                }
            }
            return 'visible tags: ' + JSON.stringify(found);
        })()
    """, "[5b/7] 可见标签")

    time.sleep(1)

    # Try clicking 后端 tag again
    pe(tid, """
        (() => {
            for(let el of document.querySelectorAll('*')) {
                if(el.innerText.trim() === '后端' && el.offsetParent !== null) {
                    el.click(); return 'clicked 后端';
                }
            }
            return 'tag 后端 not visible';
        })()
    """, "[5c/7] 点击后端标签")

    time.sleep(1)

    # 6. Click 确定并发布
    pe(tid, """
        (() => {
            for(let b of document.querySelectorAll('button')) {
                if(b.innerText.trim() === '确定并发布' && b.offsetParent !== null) {
                    b.click(); return 'clicked';
                }
            }
            return 'not found';
        })()
    """, "[6/7] 确定并发布")
    time.sleep(5)

    # 7. Check result
    result = pe(tid, """
        (() => {
            let txt = document.body.innerText.substring(0, 300);
            let url = location.href;
            let title = document.title;
            // Check for success notification
            let success = txt.includes('发布成功') || txt.includes('文章已发布');
            let articleMatch = url.match(/\/post\/(\d+)/);
            return JSON.stringify({title, url, success, hasArticleId: !!articleMatch, articleId: articleMatch ? articleMatch[1] : null, body: txt.substring(0, 200)});
        })()
    """, "[7/7] 结果")

    if result:
        if '"success":true' in result or 'hasArticleId' in result and 'true' in result:
            print("\n  ✅ 文章发布成功！")
        else:
            print("\n  ⚠️ 可能仍需手动操作")
            print(f"  草稿地址: {draft_url}")
    else:
        print("\n  ❌ 发布失败")
        print(f"  草稿地址: {draft_url}")

if __name__ == "__main__":
    main()
