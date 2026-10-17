#include "network_detector.h"

#include <ws2tcpip.h>
#include <iphlpapi.h>
#include <shellapi.h>

#include <vector>

#pragma comment(lib, "iphlpapi.lib")
#pragma comment(lib, "ws2_32.lib")

namespace rmtt {

bool NetworkDetector::IsVirtualIpConfigured(const std::wstring& targetIp) {
    ULONG outBufLen = 15000;
    std::vector<BYTE> buffer(outBufLen);
    PIP_ADAPTER_ADDRESSES pAddresses = reinterpret_cast<IP_ADAPTER_ADDRESSES*>(buffer.data());

    ULONG flags = GAA_FLAG_INCLUDE_ALL_INTERFACES | GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST | GAA_FLAG_SKIP_DNS_SERVER;
    DWORD dwRetVal = GetAdaptersAddresses(AF_INET, flags, nullptr, pAddresses, &outBufLen);
    if (dwRetVal == ERROR_BUFFER_OVERFLOW) {
        buffer.resize(outBufLen);
        pAddresses = reinterpret_cast<IP_ADAPTER_ADDRESSES*>(buffer.data());
        dwRetVal = GetAdaptersAddresses(AF_INET, flags, nullptr, pAddresses, &outBufLen);
    }

    if (dwRetVal != NO_ERROR) {
        return false;
    }

    char targetUtf8[64] = {};
    WideCharToMultiByte(CP_UTF8, 0, targetIp.c_str(), -1, targetUtf8, sizeof(targetUtf8), nullptr, nullptr);

    for (PIP_ADAPTER_ADDRESSES pCurrAddresses = pAddresses; pCurrAddresses != nullptr; pCurrAddresses = pCurrAddresses->Next) {
        for (PIP_ADAPTER_UNICAST_ADDRESS pUnicast = pCurrAddresses->FirstUnicastAddress; pUnicast != nullptr; pUnicast = pUnicast->Next) {
            if (pUnicast->Address.lpSockaddr->sa_family == AF_INET) {
                sockaddr_in* sa_in = reinterpret_cast<sockaddr_in*>(pUnicast->Address.lpSockaddr);
                char ipStr[INET_ADDRSTRLEN] = {};
                inet_ntop(AF_INET, &(sa_in->sin_addr), ipStr, INET_ADDRSTRLEN);
                if (strcmp(ipStr, targetUtf8) == 0) {
                    return true;
                }
            }
        }
    }
    return false;
}

bool NetworkDetector::LaunchSetupNetworkScript(HWND parentHwnd, const std::wstring& scriptPath) {
    SHELLEXECUTEINFOW sei = { sizeof(sei) };
    sei.cbSize = sizeof(sei);
    sei.fMask = SEE_MASK_NOCLOSEPROCESS;
    sei.hwnd = parentHwnd;
    sei.lpVerb = L"runas"; // 请求 UAC 管理员权限执行
    sei.lpFile = L"powershell.exe";
    std::wstring params = L"-NoProfile -ExecutionPolicy Bypass -File \"" + scriptPath + L"\"";
    sei.lpParameters = params.c_str();
    sei.nShow = SW_SHOWNORMAL;

    if (ShellExecuteExW(&sei)) {
        if (sei.hProcess) {
            WaitForSingleObject(sei.hProcess, 15000);
            CloseHandle(sei.hProcess);
        }
        return true;
    }
    return false;
}

std::wstring NetworkDetector::GetStatusDescription() {
    bool ok1 = IsVirtualIpConfigured(L"192.168.10.1");
    if (ok1) {
        return L"网络已就绪 (192.168.10.1 在线)";
    }
    return L"未配置 (需点击「一键配置网络」)";
}

} // namespace rmtt
