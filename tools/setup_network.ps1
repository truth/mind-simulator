<#
.SYNOPSIS
  为 RoboMaster TT 模拟器配置本机虚拟 IP（需要管理员权限）。

.DESCRIPTION
  Mind+ 实时模式固定向 192.168.10.1:8889 发送 Tello SDK 指令。
  本脚本把以下地址添加到 Windows 的 "Loopback Pseudo-Interface 1"（环回接口）上：
    192.168.10.2  ── 客户端（Mind+）源地址
    192.168.10.1  ── 模拟飞机 #1（SkipAsSource，避免被当作源地址）
    192.168.10.11 起 ── 模拟飞机 #2、#3 …（使用 -Drones 指定数量时）
  并添加防火墙入站规则（UDP 8889 / 8989 / …），让同一 WiFi 下的手机 App 可以连接模拟器。
  地址只写入活动存储（ActiveStore），重启电脑后自动消失，不会影响真实网卡。

.EXAMPLE
  .\setup_network.ps1              # 默认准备 4 架（单机 / 双机模式均可直接用）
  .\setup_network.ps1 -Drones 6    # 六架飞机
  .\setup_network.ps1 -Remove      # 移除所有地址与防火墙规则
#>
param(
  [int]$Drones = 4,   # 预先准备 4 架飞机的地址和端口，单机 / 双机模式都不必重新配置
  [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host '需要管理员权限，正在请求提权...' -ForegroundColor Yellow
  $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Drones $Drones"
  if ($Remove) { $argList += ' -Remove' }
  Start-Process powershell -Verb RunAs -ArgumentList $argList -Wait
  exit
}

$ifIndex = (Get-NetIPInterface -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -like 'Loopback*' } | Select-Object -First 1).InterfaceIndex
if (-not $ifIndex) { $ifIndex = 1 }

$client = '192.168.10.2'
$droneIps = @('192.168.10.1')
for ($i = 2; $i -le $Drones; $i++) { $droneIps += "192.168.10.$(9 + $i)" }

function Remove-SimIp([string]$ip) {
  Get-NetIPAddress -IPAddress $ip -ErrorAction SilentlyContinue | Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
}

if ($Remove) {
  $all = @($client, '192.168.10.1') + (11..30 | ForEach-Object { "192.168.10.$_" })
  foreach ($ip in $all) { Remove-SimIp $ip }
  Get-NetFirewallRule -DisplayName 'RoboMaster TT Simulator (UDP)' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
  Get-NetFirewallRule -DisplayName 'RoboMaster TT Simulator Discovery (UDP 8899)' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
  Write-Host '已移除模拟器虚拟地址。' -ForegroundColor Green
  exit
}

# 检查真实网络是否已经处于 192.168.10.x 网段（例如电脑正连着真飞机的 WiFi）
$conflict = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -like '192.168.10.*' -and $_.InterfaceIndex -ne $ifIndex }
if ($conflict) {
  Write-Host "警告：网卡 $($conflict[0].InterfaceAlias) 已使用 $($conflict[0].IPAddress)（可能连接着真实飞机），与模拟器地址冲突。" -ForegroundColor Red
  Write-Host '请先断开该网络后再运行本脚本。'
  Read-Host '按回车退出'
  exit 1
}

function Add-SimIp([string]$ip, [bool]$skip) {
  $exist = Get-NetIPAddress -IPAddress $ip -ErrorAction SilentlyContinue
  if ($exist) {
    if ($exist.InterfaceIndex -eq $ifIndex -and $exist.SkipAsSource -eq $skip) { return }
    Remove-SimIp $ip
  }
  New-NetIPAddress -InterfaceIndex $ifIndex -IPAddress $ip -PrefixLength 24 -SkipAsSource $skip -PolicyStore ActiveStore | Out-Null
}

# 防火墙：允许手机 App 经局域网访问模拟器（飞机 #1 端口 8889，#2 起 8989、9089 …）
$ports = @(1..$Drones | ForEach-Object { 8889 + 100 * ($_ - 1) })
$ruleName = 'RoboMaster TT Simulator (UDP)'
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol UDP -LocalPort $ports -Action Allow -Profile Any | Out-Null
Write-Host "已添加防火墙入站规则：UDP $($ports -join ', ')" -ForegroundColor Green
# 自动发现：手机 App 广播搜索模拟器
$discoveryRule = 'RoboMaster TT Simulator Discovery (UDP 8899)'
Get-NetFirewallRule -DisplayName $discoveryRule -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $discoveryRule -Direction Inbound -Protocol UDP -LocalPort 8899 -Action Allow -Profile Any | Out-Null
Write-Host '已添加防火墙入站规则：UDP 8899（自动发现）' -ForegroundColor Green

# 先添加客户端地址，保证它成为 192.168.10.0/24 的首选源地址
Add-SimIp $client $false
foreach ($ip in $droneIps) { Add-SimIp $ip $true }

Write-Host ''
Write-Host '环回接口地址配置完成：' -ForegroundColor Green
Get-NetIPAddress -InterfaceIndex $ifIndex -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.10.*' } |
  Sort-Object IPAddress | Format-Table IPAddress, PrefixLength, SkipAsSource -AutoSize
Write-Host ('飞机地址：' + ($droneIps -join ', '))
Write-Host '提示：地址在重启后失效，需要重新运行本脚本（start.bat 会自动检查）。'
