#pragma once

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif

#include <winsock2.h>
#include <windows.h>
#include <string>

namespace rmtt {

class NetworkDetector {
public:
    // 检查指定虚拟 IP (如 192.168.10.1) 是否已绑定在系统适配器上
    static bool IsVirtualIpConfigured(const std::wstring& targetIp = L"192.168.10.1");

    // 触发以管理员权限执行 tools\setup_network.ps1 配置虚拟 IP 与防火墙
    static bool LaunchSetupNetworkScript(HWND parentHwnd, const std::wstring& scriptPath);

    // 格式化当前网络状态文本
    static std::wstring GetStatusDescription();
};

} // namespace rmtt
