@echo off
setlocal
cd /d "%~dp0"
title RoboMaster TT 模拟器

where python >nul 2>nul || (
  echo [错误] 未找到 Python，请先安装 Python 3.8 及以上版本并勾选 Add to PATH。
  pause & exit /b 1
)

rem 检查 192.168.10.1 是否已配置，未配置则自动提权运行网络设置脚本
powershell -NoProfile -Command "if ((Get-NetIPAddress -IPAddress 192.168.10.1 -ErrorAction SilentlyContinue) -and (Get-NetFirewallRule -DisplayName 'RoboMaster TT Simulator (UDP)' -ErrorAction SilentlyContinue)) { exit 0 } else { exit 1 }"
if errorlevel 1 (
  echo 首次运行：正在配置虚拟 IP 192.168.10.1 和防火墙规则（需要管理员权限，请在弹窗中点“是”）...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\setup_network.ps1"
)

python -m rmtt_sim %*
pause
