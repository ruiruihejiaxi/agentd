#!/usr/bin/env python3
"""删除掘金文章 — CDP 浏览器操作"""
import sys, json, time, urllib.request, urllib.parse

CDP = "http://127.0.0.1:3456"

def get(path):
    for i in range(3):
        try:
            with urllib.request.urlopen(f"{CDP}{path}", timeout=20) as r:
                return json.loads(r.read())
        except:
            if i < 2: time.sleep(2)
            else: raise

def post(path, data=None):
    for i in range(3):
        try:
            req = urllib.request.Request(
                f"{CDP}{path}", data=data.encode() if data else None,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except:
            if i < 2: time.sleep(2)
            else: raise

def pe(tid, js):
    for i in range(3):
        try:
            r = post(f"/eval?target={tid}", js)
            return r.get("value") if "error" not in r else None
        except:
            if i < 2: time.sleep(2)
            else: return None

# Open article management
print("[1] 打开文章管理...")
r = get(f"/new?url={urllib.parse.quote('https://juejin.cn/creator/content/article/essays?status=all')}")
tid = r.get("targetId")
time.sleep(5)

# Find and click the article row
print("[2] 点击文章行...")
pe(tid, """
(() => {
    let all = document.querySelectorAll('*');
    for(let el of all) {
        let t = el.innerText.trim();
        if(t.includes('多Agent协作系统') && el.offsetParent !== null && el.tagName === 'DIV') {
            el.click();
            return 'clicked';
        }
    }
    return 'not found';
})()
""")
time.sleep(2)

# Now check for action buttons
pe(tid, """
(() => {
    let all = document.querySelectorAll('*');
    let found = [];
    all.forEach(el => {
        let t = el.innerText.trim();
        if(el.offsetParent !== null && t && t.length < 10) {
            let c = (el.className || '');
            if(t.includes('删除') || t.includes('下架') || c.includes('delete') || c.includes('del')) {
                found.push({tag: el.tagName, text: t, class: c.substring(0, 40)});
            }
        }
    });
    return 'action btns: ' + JSON.stringify(found);
})()
""")
time.sleep(1)

# Try to find a more button or delete option via API
# Search for article list actions
pe(tid, """
(async () => {
    function xhr(url, data) {
        return new Promise(r => {
            let x = new XMLHttpRequest();
            x.open('POST', url, true);
            x.setRequestHeader('Content-Type', 'application/json');
            x.withCredentials = true;
            x.onload = () => r(JSON.parse(x.responseText));
            x.send(JSON.stringify(data));
        });
    }

    // Try to delete via API - juejin content delete
    const resp = await xhr('https://api.juejin.cn/content_api/v1/article/delete?aid=2608', {
        article_id: '7638980719160950819'
    });
    return 'delete result: ' + JSON.stringify(resp);
})()
""")
time.sleep(2)

# Final check
final = pe(tid, "JSON.stringify({title: document.title, url: location.href})")
print(f"[结果] {final}")
