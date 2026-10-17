#pragma once

#include <Windows.h>
#include <string>
#include <vector>
#include <deque>
#include <mutex>
#include <thread>
#include <atomic>

namespace rmtt {

class ProcessManager {
public:
    ProcessManager();
    ~ProcessManager();

    // 启动 Python 模拟器引擎子进程
    bool Start(const std::wstring& pythonExe, const std::wstring& workDir, const std::wstring& arguments);

    // 优雅停止 Python 进程
    bool Stop();

    // 检查子进程是否处于活动状态
    bool IsRunning();

    // 获取进程运行秒数
    DWORD GetUptimeSeconds() const;

    // 获取最近的日志文本 (用于更新界面 txt_console)
    std::wstring GetRecentLogs(size_t maxLines = 100);

    // 清空日志缓冲区
    void ClearLogs();

    // 手动追加一条管理日志
    void AddLog(const std::wstring& line);

    // 查找适用的 Python 运行程序路径 (优先 runtime/python，次选系统 python)
    static std::wstring FindPythonExecutable(const std::wstring& baseDir);

private:
    void ReaderThreadFunc();

    HANDLE m_hProcess = nullptr;
    HANDLE m_hThread = nullptr;
    HANDLE m_hReadPipe = nullptr;
    DWORD m_processId = 0;
    ULONGLONG m_startTimeTick = 0;

    std::thread m_readerThread;
    std::atomic<bool> m_stopReader{false};

    mutable std::mutex m_logMutex;
    std::deque<std::wstring> m_logLines;
};

} // namespace rmtt
