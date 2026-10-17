#pragma once

#include <windows.h>
#include <winhttp.h>
#include <string>
#include <thread>
#include <vector>

#pragma comment(lib, "winhttp.lib")

namespace rmtt {

class SimHttpClient {
public:
    // 同步发送 POST 请求 (带短超时，避免阻塞)
    static bool PostJson(int port, const std::wstring& path, const std::string& jsonBody) {
        HINTERNET hSession = WinHttpOpen(L"RoboMasterTT-Desktop/1.0",
                                         WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                         WINHTTP_NO_PROXY_NAME,
                                         WINHTTP_NO_PROXY_BYPASS, 0);
        if (!hSession) return false;

        HINTERNET hConnect = WinHttpConnect(hSession, L"127.0.0.1", static_cast<INTERNET_PORT>(port), 0);
        if (!hConnect) {
            WinHttpCloseHandle(hSession);
            return false;
        }

        HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"POST", path.c_str(),
                                               nullptr, WINHTTP_NO_REFERER,
                                               WINHTTP_DEFAULT_ACCEPT_TYPES, 0);
        if (!hRequest) {
            WinHttpCloseHandle(hConnect);
            WinHttpCloseHandle(hSession);
            return false;
        }

        // 超时设置：连接 300ms，发送 300ms，接收 500ms
        WinHttpSetTimeouts(hRequest, 300, 300, 500, 500);

        std::wstring headers = L"Content-Type: application/json; charset=utf-8\r\n";
        BOOL bResults = WinHttpSendRequest(hRequest,
                                          headers.c_str(), static_cast<DWORD>(headers.length()),
                                          (LPVOID)jsonBody.c_str(), static_cast<DWORD>(jsonBody.length()),
                                          static_cast<DWORD>(jsonBody.length()), 0);

        if (bResults) {
            bResults = WinHttpReceiveResponse(hRequest, nullptr);
        }

        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return bResults == TRUE;
    }

    // 异步发送 POST 请求，保证 UI 绝对流畅零卡顿
    static void PostJsonAsync(int port, const std::wstring& path, const std::string& jsonBody) {
        std::thread([port, path, jsonBody]() {
            PostJson(port, path, jsonBody);
        }).detach();
    }

    // 同步拉取 GET JSON 数据 (带短超时)
    static bool GetJson(int port, const std::wstring& path, std::string& outJson) {
        HINTERNET hSession = WinHttpOpen(L"RoboMasterTT-Desktop/1.0",
                                         WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                         WINHTTP_NO_PROXY_NAME,
                                         WINHTTP_NO_PROXY_BYPASS, 0);
        if (!hSession) return false;

        HINTERNET hConnect = WinHttpConnect(hSession, L"127.0.0.1", static_cast<INTERNET_PORT>(port), 0);
        if (!hConnect) {
            WinHttpCloseHandle(hSession);
            return false;
        }

        HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"GET", path.c_str(),
                                               nullptr, WINHTTP_NO_REFERER,
                                               WINHTTP_DEFAULT_ACCEPT_TYPES, 0);
        if (!hRequest) {
            WinHttpCloseHandle(hConnect);
            WinHttpCloseHandle(hSession);
            return false;
        }

        // 短超时 300ms
        WinHttpSetTimeouts(hRequest, 300, 300, 400, 400);

        BOOL bResults = WinHttpSendRequest(hRequest,
                                          WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                                          WINHTTP_NO_REQUEST_DATA, 0, 0, 0);

        if (bResults) {
            bResults = WinHttpReceiveResponse(hRequest, nullptr);
        }

        if (bResults) {
            DWORD dwSize = 0;
            DWORD dwDownloaded = 0;
            outJson.clear();
            do {
                dwSize = 0;
                if (!WinHttpQueryDataAvailable(hRequest, &dwSize)) break;
                if (dwSize == 0) break;
                std::vector<char> buffer(dwSize + 1);
                if (WinHttpReadData(hRequest, buffer.data(), dwSize, &dwDownloaded)) {
                    outJson.append(buffer.data(), dwDownloaded);
                }
            } while (dwSize > 0);
        }

        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return bResults == TRUE;
    }
};

} // namespace rmtt
