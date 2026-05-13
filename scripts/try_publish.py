import asyncio, json, websockets

TID = "87FCE26C0C8F1965AF337C11A31F48C9"

async def cdp(ws, expr, timeout=25):
    cmd = {"id": 1, "method": "Runtime.evaluate", "params": {
        "expression": expr, "returnByValue": True,
        "awaitPromise": True, "timeout": int(timeout * 1000)
    }}
    await ws.send(json.dumps(cmd))
    raw = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout + 5))
    return raw.get("result", {}).get("result", {}).get("value")

async def main():
    async with websockets.connect(f"ws://localhost:9222/devtools/page/{TID}", max_size=10*1024*1024) as ws:
        await asyncio.sleep(2)

        # Check user profile first
        print("=== Check profile ===")
        r = await cdp(ws, """
        (async () => {
            var r = await fetch('/user_api/v1/user/get?user_id=4315996579959984', {credentials: 'include'});
            var d = await r.json();
            return JSON.stringify({name: d.data.user_name, level: d.data.level, job: d.data.job_title});
        })()
        """)
        print(f"Profile: {r}")

        # Create draft with simple content (no URL, no special chars)
        print("\n=== Create simple draft ===")
        r2 = await cdp(ws, """
        (async () => {
            try {
                var resp = await fetch('https://juejin.cn/content_api/v1/article_draft/create', {
                    method: 'POST', credentials: 'include',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        title: '写代码不跑一遍，你永远不知道有多少坑',
                        content: '前阵子写了一个多 Agent 协作框架，代码写完自我感觉良好，build 全过，commit 完事。\\n\\n然后有人问我：你自己跑过没有？\\n\\n我愣住了。还真没有。\\n\\n于是真的跑了一遍，发现问题比想象的多十倍：\\n\\n1. 端口被占，webui 直接挂\\n2. 环境变量名不一致导致崩溃\\n3. 文件没初始化，收不到消息\\n4. 入口文件太多，不知道该点哪个\\n5. 路径写死，换个目录就炸\\n6. Windows 下中文乱码\\n7. 界面没有任何引导提示\\n\\n全是低级问题，但写的时候一个都没注意到。\\n\\n写代码的时候你在想这个功能怎么实现，打开项目的时候你在想这个东西怎么用。这两个视角之间的差距，就是所有问题的根源。\\n\\n写完不是终点，跑一遍才算。'
                    })
                });
                var data = await resp.json();
                return JSON.stringify(data);
            } catch(e) { return 'Error: ' + e.message; }
        })()
        """)
        print(f"Create: {r2}")

        try:
            d2 = json.loads(r2) if r2 else {}
            did = (d2.get("data") or {}).get("id", "")
            if did:
                print(f"\n=== Publish draft {did} ===")
                r3 = await cdp(ws, f"""
                (async () => {{
                    try {{
                        var resp = await fetch('https://juejin.cn/content_api/v1/article/publish', {{
                            method: 'POST', credentials: 'include',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{draft_id: '{did}'}})
                        }});
                        var data = await resp.json();
                        return JSON.stringify(data);
                    }} catch(e) {{ return 'Error: ' + e.message; }}
                }})()
                """)
                print(f"Publish: {r3}")
        except:
            pass

asyncio.run(main())
