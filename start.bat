@echo off
chcp 65001 >nul
title agentd 启动面板

echo ============================================
echo   agentd - 多 Agent 协作系统启动面板
echo ============================================
echo.

:: 设置 Python 编码
set PYTHONIOENCODING=utf-8

:: 检查端口占用
:check_ports
echo [检查] 检查端口状态...
set PORT_BUSY=0
for %%p in (3001 3010 3011) do (
    netstat -ano | findstr "0.0.0.0:%%p " >nul 2>&1
    if !errorlevel! equ 0 (
        echo [警告] 端口 %%p 已被占用
        set PORT_BUSY=1
    )
)

if "%PORT_BUSY%"=="1" (
    echo.
    echo 需要先释放端口吗？按 K 杀掉占用进程，按其他键继续...
    choice /c KN /n /t 5 /d N >nul
    if errorlevel 2 goto :continue
    if errorlevel 1 (
        echo [操作] 正在清理端口...
        for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3001 "') do (
            if not "%%a"=="" taskkill -f -pid %%a >nul 2>&1
        )
        for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3010 "') do (
            if not "%%a"=="" taskkill -f -pid %%a >nul 2>&1
        )
        for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3011 "') do (
            if not "%%a"=="" taskkill -f -pid %%a >nul 2>&1
        )
        timeout /t 2 >nul
        echo [完成] 端口已清理
    )
)

:continue
echo.
echo ===== 选择启动模式 =====
echo 1. 完整启动 (调度器 + 所有 Agent + UI)
echo 2. 仅启动调度器 (agentd + UI)
echo 3. 仅启动 Agent 桥接服务
echo 4. 启动 Web 控制台 (端口 8080)
echo 5. 查看余额
echo 6. 退出
echo.

choice /c 123456 /n /t 15 /d 1 /m "请选择 (1-6，默认1)："

if errorlevel 6 exit /b
if errorlevel 5 goto :balance
if errorlevel 4 goto :webui
if errorlevel 3 goto :bridges_only
if errorlevel 2 goto :scheduler_only
if errorlevel 1 goto :full_start

:webui
echo.
echo [启动] 启动 Web 控制台 (端口 8080)...
start "agentd-WebUI" cmd /c "cd /d D:\agentd && python webui.py"
timeout /t 2 >nul
echo [完成] Web 控制台已启动: http://localhost:8080
echo.
echo 按任意键返回...
pause >nul
goto :continue

:balance
echo.
python scripts\survival.py --history
echo.
echo 按任意键返回...
pause >nul
goto :continue

:bridges_only
echo.
echo [启动] 启动 WorkBuddy bridge (端口 3010)...
start "WorkBuddy" cmd /c "cd /d D:\agentd && set LLM_API_KEY=%LLM_API_KEY% && python bridges\workbuddy\workbuddy_bridge.py"

echo [启动] 启动 CodeBuddy bridge (端口 3011)...
start "CodeBuddy" cmd /c "cd /d D:\agentd && set BRIDGE_NAME=CodeBuddy && set BRIDGE_PORT=3011 && set LLM_API_KEY=%LLM_API_KEY% && set LLM_API_URL=https://api.deepseek.com/v1/chat/completions && set LLM_MODEL=deepseek-chat && python bridges\universal_bridge.py"

timeout /t 3 >nul
echo [完成] Agent 桥接服务已启动
echo.
echo 查看状态: http://localhost:3010/health (WorkBuddy)
echo 查看状态: http://localhost:3011/health (CodeBuddy)
echo.
echo 按任意键返回...
pause >nul
goto :continue

:scheduler_only
echo.
echo [启动] 启动调度器 agentd (端口 3001)...
start "agentd" cmd /c "cd /d D:\agentd && python agentd.py --session default"

timeout /t 3 >nul
echo [完成] 调度器已启动
echo.
echo 按任意键返回...
pause >nul
goto :continue

:full_start
echo.
echo [启动] 正在启动 agentd 完整系统...

:: 1. Agent bridges
echo [1/3] 启动 WorkBuddy bridge...
start "WorkBuddy" cmd /c "cd /d D:\agentd && set LLM_API_KEY=%LLM_API_KEY% && python bridges\workbuddy\workbuddy_bridge.py"

echo [1/3] 启动 CodeBuddy bridge...
start "CodeBuddy" cmd /c "cd /d D:\agentd && set BRIDGE_NAME=CodeBuddy && set BRIDGE_PORT=3011 && set LLM_API_KEY=%LLM_API_KEY% && set LLM_API_URL=https://api.deepseek.com/v1/chat/completions && set LLM_MODEL=deepseek-chat && python bridges\universal_bridge.py"

timeout /t 3 >nul

:: 2. Scheduler
echo [2/3] 启动调度器 agentd...
start "agentd" cmd /c "cd /d D:\agentd && python agentd.py --session default"

timeout /t 3 >nul

:: 3. UI
echo [3/3] 启动用户界面...
start "agentd-UI" cmd /c "cd /d D:\agentd && python ui.py"

echo.
echo ============================================
echo   agentd 系统启动完成!
echo   调度器:     http://localhost:3001/api/status
echo   WorkBuddy:  http://localhost:3010/health
echo   CodeBuddy:  http://localhost:3011/health
echo ============================================
echo.
echo 关闭所有窗口可结束系统运行。
echo.
exit /b
