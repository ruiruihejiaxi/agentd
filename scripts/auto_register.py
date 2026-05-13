#!/usr/bin/env python3
"""
自动注册脚本 — 通过 CDP 代理操控浏览器完成平台注册
用法: python auto_register.py juejin
"""
import sys
import json
import time
import urllib.request
import urllib.parse

CDP_PROXY = "http://127.0.0.1:3456"

def cdp_get(path):
    with urllib.request.urlopen(f"{CDP_PROXY}{path}", timeout=10) as r:
        return json.loads(r.read())

def cdp_post(path, data=None):
    req = urllib.request.Request(
        f"{CDP_PROXY}{path}",
        data=data.encode() if data else None,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def new_page(url):
    result = cdp_get(f"/new?url={urllib.parse.quote(url)}")
    target_id = result.get("targetId", result.get("targetId"))
    print(f"  打开页面: {url}")
    return target_id

def page_eval(target_id, js):
    result = cdp_post(f"/eval?target={target_id}", js)
    if "error" in result:
        print(f"  JS错误: {result['error']}")
        return None
    return result.get("value")

def page_click(target_id, selector_text):
    result = cdp_post(f"/click?target={target_id}", selector_text)
    return result.get("value") or result.get("error")

def page_info(target_id):
    return cdp_get(f"/info?target={target_id}")

def register_juejin():
    """掘金验证码登录/注册"""
    print("\n[掘金] 开始注册...")

    target = new_page("https://juejin.cn/login")
    time.sleep(4)

    info = page_info(target)
    print(f"  页面: {info.get('title', '?')}")

    # 检查页面是否加载成功
    if "登录" not in info.get("title", ""):
        print(f"  [!] 页面未正确加载")
        return False

    # 找输入框填手机号
    js_fill = """
    (() => {
        let inputs = document.querySelectorAll('input');
        for(let inp of inputs) {
            if(inp.type === 'tel' || inp.placeholder.includes('手机') || inp.type === 'text') {
                let nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                nativeInputValueSetter.call(inp, '15330309682');
                inp.dispatchEvent(new Event('input', {bubbles: true}));
                inp.dispatchEvent(new Event('change', {bubbles: true}));
                return 'filled: ' + inp.value;
            }
        }
        return 'no input found';
    })()
    """
    result = page_eval(target, js_fill)
    print(f"  填号: {result}")
    time.sleep(1)

    # 找获取验证码按钮
    js_btn = """
    (() => {
        let all = document.querySelectorAll('button, span, a, div, p');
        for(let el of all) {
            let t = el.innerText.trim();
            if(t.includes('验证码') || t.includes('获取')) {
                el.click();
                return 'clicked: ' + t;
            }
        }
        return 'no button found';
    })()
    """
    result = page_eval(target, js_btn)
    print(f"  点击发送验证码: {result}")

    if result and "no button" in result:
        # 试试看找所有可点击元素
        js_all = "Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim())"
        btns = page_eval(target, js_all)
        print(f"  页面按钮: {btns}")
        return False

    print(f"\n  === 请查收手机短信验证码 ===")
    print(f"  手机号: 15330309682")
    print(f"  收到验证码后输入以下命令继续:")
    print(f"  python auto_register.py juejin_code <验证码>")
    return True

def register_juejin_code(code):
    """输入验证码完成注册"""
    print(f"\n[掘金] 输入验证码: {code}")

    target = cdp_get("/targets")
    # 找已打开的掘金登录页面
    print(f"  需要手动操作: 请在浏览器中填入验证码 {code}")
    return True

def main():
    if len(sys.argv) < 2:
        print("用法: python auto_register.py <平台>")
        print("平台: juejin, zhihu, csdn")
        return

    cmd = sys.argv[1]

    if cmd == "juejin":
        register_juejin()
    elif cmd == "juejin_code" and len(sys.argv) >= 3:
        register_juejin_code(sys.argv[2])
    else:
        print(f"未知命令: {cmd}")

if __name__ == "__main__":
    main()
