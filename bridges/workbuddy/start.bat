@echo off
REM WorkBuddy Bridge 启动脚本
REM 使用方法：双击运行此脚本，或在命令行执行

REM 设置 API Key 环境变量（请先设置 DEEPSEEK_API_KEY 环境变量）
REM 临时方案：取消注释下面一行并填入你的 Key
REM set DEEPSEEK_API_KEY=your_key_here

REM 启动服务
echo [WorkBuddy] 启动 HTTP 服务...
python "%~dp0workbuddy_bridge.py"
