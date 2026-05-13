#!/usr/bin/env python3
"""
agentd 免费 LLM 备用方案一键配置工具
当 DeepSeek 余额不足时，切换到免费/低价 LLM 提供商
"""
import os
import sys
import json
import subprocess
from pathlib import Path

BASE_DIR = str(Path(__file__).parent.parent)

def log(msg):
    print(f"  {msg}")

def setup_openrouter(key):
    """配置 OpenRouter"""
    configs = {
        "bridges/universal_bridge.py": {
            "LLM_API_KEY": key,
            "LLM_API_URL": "https://openrouter.ai/api/v1/chat/completions",
            "LLM_MODEL": "google/gemma-4-26b-a4b-it:free",
        },
        "bridges/workbuddy/env.example": {
            "OPENROUTER_KEY": key,
        }
    }

    # 写入 .env 文件供 bridge 读取
    env_file = os.path.join(BASE_DIR, ".env.openrouter")
    with open(env_file, "w") as f:
        f.write(f'OPENROUTER_API_KEY={key}\n')
        f.write(f'LLM_API_URL=https://openrouter.ai/api/v1/chat/completions\n')
        f.write(f'LLM_MODEL=google/gemma-4-26b-a4b-it:free\n')
    log(f"配置已写入: {env_file}")

def setup_deepseek_fallback():
    """配置余额不足时自动降级到省钱模式"""
    script = os.path.join(BASE_DIR, "scripts", "survival.py")
    env_file = os.path.join(BASE_DIR, ".env.bridge")

    with open(env_file, "w") as f:
        f.write("# agentd bridge 环境配置\n")
        f.write("# 当余额低于阈值时，自动切换到省钱模型\n\n")
        f.write("# 当前使用的 API 配置\n")
        f.write('LLM_API_KEY=YOUR_API_KEY_HERE  # 从环境变量 DEEPSEEK_API_KEY 获取\n')
        f.write('LLM_API_URL=https://api.deepseek.com/v1/chat/completions\n')
        f.write('LLM_MODEL=deepseek-chat\n\n')
        f.write("# 省钱备用配置 (余额低于 1 CNY 时启用)\n")
        f.write('# 1. 配置 OpenRouter 免费模型:\n')
        f.write('# LLM_API_URL=https://openrouter.ai/api/v1/chat/completions\n')
        f.write('# LLM_MODEL=google/gemma-4-26b-a4b-it:free\n')
        f.write('# 需要有效的 OpenRouter API Key\n')
    log(f"备用配置已创建: {env_file}")

def check_alternatives():
    """检查可用的免费 LLM 提供商"""
    print()
    log("可用的免费 LLM 替代方案:")
    print()
    log("1. OpenRouter - 26个免费模型")
    log("   注册: https://openrouter.ai/signup")
    log("   免费: Gemma 4, Nemotron, 及其他社区模型")
    log("   需要: 注册账号获取 API Key")
    print()
    log("2. Google AI Studio (Gemini)")
    log("   注册: https://aistudio.google.com/apikey")
    log("   免费: Gemini 2.0 Flash (60次/分钟)")
    log("   需要: Google 账号 + API Key")
    print()
    log("3. GitHub Models")
    log("   需要: GitHub token 添加 'models' 权限")
    log("   免费: Azure AI 模型, 有速率限制")
    print()
    log("4. Hugging Face Inference API")
    log("   免费: 部分模型免费")
    log("   需要: Hugging Face 账号")
    print()

def show_status():
    """显示当前 DeepSeek 余额和消耗趋势"""
    try:
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "scripts", "survival.py"), "--history"])
    except:
        log("无法查询余额")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="agentd 免费 LLM 配置工具")
    parser.add_argument("action", nargs="?", default="status",
                        choices=["status", "setup", "check", "help"],
                        help="操作: status=查看余额, setup=创建备用配置, check=查看可用选项")
    args = parser.parse_args()

    print("=" * 50)
    print("  agentd 生存配置工具")
    print("  Balance = Life")
    print("=" * 50)

    if args.action == "status":
        show_status()
    elif args.action == "check":
        check_alternatives()
    elif args.action == "setup":
        setup_deepseek_fallback()
        log("备用配置已设置完成")
        log("提示: 需要 OpenRouter 账号才能启用免费模型")

        key = os.environ.get("OPENROUTER_API_KEY")
        if key:
            setup_openrouter(key)
    elif args.action == "help":
        check_alternatives()
        print()
        log("使用方式:")
        log("  python scripts/survival_config.py status  查看余额")
        log("  python scripts/survival_config.py check   查看免费替代方案")
        log("  python scripts/survival_config.py setup   创建备用配置")
        print()

if __name__ == "__main__":
    main()
