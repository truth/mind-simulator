#include "process_manager.h"

#include <shlwapi.h>
#include <sstream>

#pragma comment(lib, "shlwapi.lib")

namespace rmtt {

namespace {

std::wstring Utf8ToUtf16(const std::string& str) {
    if (str.empty()) return std::wstring();
    // 使用明确长度转换，避免写入空终止符导致越界
    int len = MultiByteToWideChar(CP_UTF8, 0, str.data(), static_cast<int>(str.size()), nullptr, 0);
    if (len <= 0) {
        // 若非标准 UTF-8 则尝试以 ANSI (GBK) 转换
        len = MultiByteToWideChar(CP_ACP, 0, str.data(), static_cast<int>(str.size()), nullptr, 0);
        if (len <= 0) return std::wstring();
        std::wstring result(len, L'\0');
        MultiByteToWideChar(CP_ACP, 0, str.data(), static_cast<int>(str.size()), result.data(), len);
        return result;
    }
    std::wstring result(len, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, str.data(), static_cast<int>(str.size()), result.data(), len);
    return result;
}

} // namespace

ProcessManager::ProcessManager() {}

ProcessManager::~ProcessManager() {
    Stop();
}

bool ProcessManager::Start(const std::wstring& pythonExe, const std::wstring& workDir, const std::wstring& arguments) {
    if (IsRunning()) {
        return true;
    }

    // 确保旧读取线程已停止
    if (m_readerThread.joinable()) {
        m_stopReader = true;
        if (m_hReadPipe) {
            CloseHandle(m_hReadPipe);
            m_hReadPipe = nullptr;
        }
        m_readerThread.join();
    }

    SECURITY_ATTRIBUTES saAttr{};
    saAttr.nLength = sizeof(SECURITY_ATTRIBUTES);
    saAttr.bInheritHandle = TRUE;
    saAttr.lpSecurityDescriptor = nullptr;

    HANDLE hWritePipe = nullptr;
    if (!CreatePipe(&m_hReadPipe, &hWritePipe, &saAttr, 0)) {
        return false;
    }

    // 确保读取端句柄不被子进程继承
    SetHandleInformation(m_hReadPipe, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOW si{};
    si.cb = sizeof(STARTUPINFOW);
    si.hStdError = hWritePipe;
    si.hStdOutput = hWritePipe;
    si.dwFlags |= STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;

    PROCESS_INFORMATION pi{};

    std::wstring cmdLine = L"\"" + pythonExe + L"\" " + arguments;
    std::vector<wchar_t> cmdBuffer(cmdLine.begin(), cmdLine.end());
    cmdBuffer.push_back(L'\0');

    BOOL success = CreateProcessW(
        nullptr,
        cmdBuffer.data(),
        nullptr,
        nullptr,
        TRUE, // 继承句柄以传递写入管道
        CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
        nullptr,
        workDir.empty() ? nullptr : workDir.c_str(),
        &si,
        &pi
    );

    // 父进程关闭写句柄，当子进程关闭时读端才能检测到 EOF
    CloseHandle(hWritePipe);

    if (!success) {
        CloseHandle(m_hReadPipe);
        m_hReadPipe = nullptr;
        return false;
    }

    m_hProcess = pi.hProcess;
    m_hThread = pi.hThread;
    m_processId = pi.dwProcessId;
    m_startTimeTick = GetTickCount64();

    {
        std::lock_guard<std::mutex> lock(m_logMutex);
        m_logLines.push_back(L"[管理中心] 模拟器引擎已启动 (PID=" + std::to_wstring(m_processId) + L")");
    }

    m_stopReader = false;
    m_readerThread = std::thread(&ProcessManager::ReaderThreadFunc, this);

    return true;
}

bool ProcessManager::Stop() {
    if (m_hProcess == nullptr) {
        AddLog(L"[管理中心] 模拟器引擎当前未处于运行状态。");
        return true;
    }

    AddLog(L"[管理中心] 正在停止模拟器引擎 (PID=" + std::to_wstring(m_processId) + L")...");

    m_stopReader = true;

    DWORD exitCode = 0;
    if (GetExitCodeProcess(m_hProcess, &exitCode) && exitCode == STILL_ACTIVE) {
        // 先发送 Ctrl+Break 尝试优雅关闭
        GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, m_processId);

        // 等待最多 500 毫秒避免主线程卡死
        if (WaitForSingleObject(m_hProcess, 500) == WAIT_TIMEOUT) {
            TerminateProcess(m_hProcess, 0);
            WaitForSingleObject(m_hProcess, 300);
        }
    }

    if (m_readerThread.joinable()) {
        // 关闭读管道唤醒 ReadFile
        if (m_hReadPipe) {
            CloseHandle(m_hReadPipe);
            m_hReadPipe = nullptr;
        }
        m_readerThread.join();
    }

    if (m_hReadPipe) {
        CloseHandle(m_hReadPipe);
        m_hReadPipe = nullptr;
    }

    if (m_hThread) {
        CloseHandle(m_hThread);
        m_hThread = nullptr;
    }
    if (m_hProcess) {
        CloseHandle(m_hProcess);
        m_hProcess = nullptr;
    }

    m_processId = 0;
    m_startTimeTick = 0;

    AddLog(L"[管理中心] 模拟器引擎已安全停止。");

    return true;
}

bool ProcessManager::IsRunning() {
    if (m_hProcess == nullptr) {
        return false;
    }
    DWORD code = 0;
    if (GetExitCodeProcess(m_hProcess, &code)) {
        return (code == STILL_ACTIVE);
    }
    return false;
}

DWORD ProcessManager::GetUptimeSeconds() const {
    if (m_startTimeTick == 0) return 0;
    return static_cast<DWORD>((GetTickCount64() - m_startTimeTick) / 1000);
}

std::wstring ProcessManager::GetRecentLogs(size_t maxLines) {
    std::lock_guard<std::mutex> lock(m_logMutex);
    std::wstring result;
    size_t count = m_logLines.size();
    size_t startIdx = (count > maxLines) ? (count - maxLines) : 0;
    for (size_t i = startIdx; i < count; ++i) {
        result += m_logLines[i];
        result += L"\r\n";
    }
    return result;
}

void ProcessManager::ClearLogs() {
    std::lock_guard<std::mutex> lock(m_logMutex);
    m_logLines.clear();
}

void ProcessManager::AddLog(const std::wstring& line) {
    std::lock_guard<std::mutex> lock(m_logMutex);
    if (m_logLines.size() > 500) {
        m_logLines.pop_front();
    }
    m_logLines.push_back(line);
}

void ProcessManager::ReaderThreadFunc() {
    char buffer[1024];
    std::string lineAccumulator;

    while (!m_stopReader && m_hReadPipe) {
        DWORD bytesRead = 0;
        BOOL ok = ReadFile(m_hReadPipe, buffer, sizeof(buffer), &bytesRead, nullptr);
        if (!ok || bytesRead == 0) {
            break;
        }

        for (DWORD i = 0; i < bytesRead; ++i) {
            char c = buffer[i];
            if (c == '\r') continue;
            if (c == '\n') {
                if (!lineAccumulator.empty()) {
                    std::wstring wline = Utf8ToUtf16(lineAccumulator);
                    if (!wline.empty()) {
                        AddLog(wline);
                    }
                    lineAccumulator.clear();
                }
            } else {
                lineAccumulator.push_back(c);
            }
        }
    }

    if (!lineAccumulator.empty()) {
        std::wstring wline = Utf8ToUtf16(lineAccumulator);
        if (!wline.empty()) {
            AddLog(wline);
        }
    }

    // 若子进程主动退出或崩溃，读取管道关闭后记录退出码
    if (m_hProcess != nullptr) {
        DWORD exitCode = 0;
        if (GetExitCodeProcess(m_hProcess, &exitCode) && exitCode != STILL_ACTIVE) {
            AddLog(L"[管理中心] 模拟器引擎子进程已退出 (代码: " + std::to_wstring(exitCode) + L")");
        }
    }
}

std::wstring ProcessManager::FindPythonExecutable(const std::wstring& baseDir) {
    // 1. 优先检查打包内置便携运行时 runtime/python/python.exe
    std::wstring embeddedPath = baseDir + L"\\runtime\\python\\python.exe";
    if (PathFileExistsW(embeddedPath.c_str())) {
        return embeddedPath;
    }

    // 2. 检查上级目录的 runtime/python/python.exe (适用于 Debug/Release 构建目录)
    std::wstring devEmbeddedPath = baseDir + L"\\..\\runtime\\python\\python.exe";
    if (PathFileExistsW(devEmbeddedPath.c_str())) {
        return devEmbeddedPath;
    }

    // 3. 检查系统标准路径 C:\Python311\python.exe
    if (PathFileExistsW(L"C:\\Python311\\python.exe")) {
        return L"C:\\Python311\\python.exe";
    }

    // 4. 回退到环境变量中的 python.exe
    return L"python.exe";
}

} // namespace rmtt
