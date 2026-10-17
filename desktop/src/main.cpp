#include "network_detector.h"
#include "process_manager.h"
#include "resource.h"

#include <ai_win_ui/host.h>
#include <ai_win_ui/observable.h>

#include <Windows.h>
#include <shellapi.h>
#include <shlwapi.h>

#include <memory>
#include <string>
#include <vector>
#include <mutex>

#pragma comment(lib, "shlwapi.lib")

namespace {

std::wstring GetModuleDir() {
    wchar_t path[MAX_PATH] = {};
    DWORD n = GetModuleFileNameW(nullptr, path, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) return L".";
    std::wstring full(path, path + n);
    size_t slash = full.find_last_of(L"\\/");
    if (slash == std::wstring::npos) return L".";
    return full.substr(0, slash);
}

std::wstring FindProjectRoot(const std::wstring& baseDir) {
    std::vector<std::wstring> candidates = {
        baseDir,
        baseDir + L"\\..",
        baseDir + L"\\..\\..",
        baseDir + L"\\..\\..\\.."
    };

    for (const auto& dir : candidates) {
        std::wstring check = dir + L"\\rmtt_sim";
        if (PathFileExistsW(check.c_str())) {
            wchar_t fullPath[MAX_PATH] = {};
            if (GetFullPathNameW(dir.c_str(), MAX_PATH, fullPath, nullptr)) {
                return std::wstring(fullPath);
            }
            return dir;
        }
    }
    return baseDir;
}

std::wstring FormatTime(DWORD totalSeconds) {
    DWORD hours = totalSeconds / 3600;
    DWORD minutes = (totalSeconds % 3600) / 60;
    DWORD seconds = totalSeconds % 60;
    wchar_t buf[32];
    swprintf_s(buf, L"%02u:%02u:%02u", hours, minutes, seconds);
    return std::wstring(buf);
}

void CopyTextToClipboard(HWND hwnd, const std::wstring& text) {
    if (!OpenClipboard(hwnd)) return;
    EmptyClipboard();
    size_t bytes = (text.size() + 1) * sizeof(wchar_t);
    HGLOBAL hMem = GlobalAlloc(GMEM_MOVEABLE, bytes);
    if (hMem) {
        void* p = GlobalLock(hMem);
        if (p) {
            memcpy(p, text.c_str(), bytes);
            GlobalUnlock(hMem);
            SetClipboardData(CF_UNICODETEXT, hMem);
        }
    }
    CloseClipboard();
}

struct AppState {
    HINSTANCE instance = nullptr;
    ai_win_ui::Host* host = nullptr;
    rmtt::ProcessManager processManager;
    std::wstring moduleDir;
    std::wstring projectRoot;
    std::wstring scene = L"pads";
    int drones = 1;
    int activeTab = 0;

    // 缓存上一次渲染的文本，仅在数据变化时触发 SetElementText，避免无谓重布局
    std::wstring lastStatus;
    std::wstring lastMindplus;
    std::wstring lastUptime;
    std::wstring lastNetStatus;
    std::wstring lastLogs;

    std::mutex actionMutex;
    std::vector<std::string> pendingActions;
};

static AppState g_appState;

void UpdateUIStatus(AppState& state);

void StartSimulator(AppState& state) {
    if (state.processManager.IsRunning()) {
        state.processManager.AddLog(L"[管理中心] 模拟器引擎已在运行中 (无需重复启动)。");
        return;
    }

    std::wstring pythonExe = rmtt::ProcessManager::FindPythonExecutable(state.projectRoot);
    std::wstring args = L"-m rmtt_sim --scene " + state.scene +
                        L" --drones " + std::to_wstring(state.drones) +
                        L" --no-browser";

    state.processManager.AddLog(L"[管理中心] 启动参数: " + args);

    bool ok = state.processManager.Start(pythonExe, state.projectRoot, args);
    if (state.host) {
        if (ok) {
            state.lastStatus = L"启动中 | UDP 8889 | 3D: 8080";
            state.host->SetElementText("lbl_status", state.lastStatus.c_str());
            state.host->SetElementBackground("indicator_dot", 0xFFF59E0B);
            state.host->SetElementForeground("lbl_status", 0xFFFBBF24);
        } else {
            state.lastStatus = L"启动失败: 未能启动 Python 进程";
            state.host->SetElementText("lbl_status", state.lastStatus.c_str());
            state.host->SetElementBackground("indicator_dot", 0xFFEF4444);
            state.host->SetElementForeground("lbl_status", 0xFFF87171);
            state.processManager.AddLog(L"[管理中心] 启动错误: 找不到 Python 引擎或 CreateProcess 失败。");
        }
    }
}

void SetActiveTab(AppState& state, int tabIndex) {
    if (tabIndex < 0 || tabIndex > 3) return;
    state.activeTab = tabIndex;
    if (state.host) {
        state.host->SelectTab("main_tabs", tabIndex);

        const char* btnNames[] = {
            "btn_nav_overview",
            "btn_nav_fleet",
            "btn_nav_network",
            "btn_nav_console"
        };
        const wchar_t* titles[] = {
            L"总览与监控",
            L"场景与多机",
            L"网络环境诊断",
            L"实时日志控制台"
        };

        for (int i = 0; i < 4; ++i) {
            if (i == tabIndex) {
                state.host->SetElementBackground(btnNames[i], 0x212631);
                state.host->SetElementForeground(btnNames[i], 0xFFFFFF);
                state.host->SetElementText(btnNames[i], (std::wstring(L"● ") + titles[i]).c_str());
            } else {
                state.host->SetElementBackground(btnNames[i], 0x14171E);
                state.host->SetElementForeground(btnNames[i], 0x94A3B8);
                state.host->SetElementText(btnNames[i], (std::wstring(L"○ ") + titles[i]).c_str());
            }
        }
    }
}

void UpdateSceneAndFleetLabels(AppState& state) {
    if (!state.host) return;

    std::wstring sceneName;
    std::wstring sceneDesc;
    if (state.scene == L"pads") {
        sceneName = L"挑战卡模式 (pads)";
        sceneDesc = L"描述：挑战卡场地包含地面与空中定位标签，支持视觉识别与精准降落。";
    } else if (state.scene == L"room") {
        sceneName = L"室内封闭房间 (room)";
        sceneDesc = L"描述：室内四壁封闭空间，适合测试避障与探索飞行。";
    } else if (state.scene == L"rings") {
        sceneName = L"穿环竞技赛道 (rings)";
        sceneDesc = L"描述：立体穿环障碍挑战场地，适合测试机动动作与计时穿越航线。";
    } else if (state.scene == L"forest") {
        sceneName = L"室外开阔树林 (forest)";
        sceneDesc = L"描述：自然障碍散布环境，适合复杂场景路径规划与室外仿真。";
    }

    state.host->SetElementText("lbl_scene_info", sceneName.c_str());
    state.host->SetElementText("lbl_cur_scene_badge", (L"当前场景: " + sceneName).c_str());
    state.host->SetElementText("lbl_scene_desc", sceneDesc.c_str());

    std::wstring dronesBadge = L"当前规模: " + std::to_wstring(state.drones) + L" 台无人机";
    state.host->SetElementText("lbl_cur_drones_badge", dronesBadge.c_str());

    std::wstring cmd = L"-m rmtt_sim --scene " + state.scene +
                       L" --drones " + std::to_wstring(state.drones) +
                       L" --no-browser";
    state.host->SetElementText("lbl_cmdline_preview", cmd.c_str());
}

void DrainPendingActions(AppState& state) {
    std::vector<std::string> actions;
    {
        std::lock_guard<std::mutex> lock(state.actionMutex);
        actions.swap(state.pendingActions);
    }

    for (const auto& actionId : actions) {
        if (actionId == "action_start") {
            StartSimulator(state);
            UpdateUIStatus(state);
        } else if (actionId == "action_stop") {
            state.processManager.Stop();
            UpdateUIStatus(state);
        } else if (actionId == "action_restart") {
            state.processManager.Stop();
            UpdateUIStatus(state);
            Sleep(200);
            StartSimulator(state);
            UpdateUIStatus(state);
        } else if (actionId == "action_open_web") {
            ShellExecuteW(nullptr, L"open", L"http://127.0.0.1:8080/", nullptr, nullptr, SW_SHOWNORMAL);
        } else if (actionId == "action_setup_net") {
            std::wstring scriptPath = state.projectRoot + L"\\tools\\setup_network.ps1";
            HWND parentHwnd = state.host ? state.host->GetHwnd() : nullptr;
            rmtt::NetworkDetector::LaunchSetupNetworkScript(parentHwnd, scriptPath);
            state.processManager.AddLog(L"[管理中心] 已触发一键网络环境配置工具 (管理员提权)");
            UpdateUIStatus(state);
        } else if (actionId == "action_recheck_net") {
            state.processManager.AddLog(L"[管理中心] 重新诊断本地网卡配置...");
            state.lastNetStatus.clear();
            UpdateUIStatus(state);
        } else if (actionId == "action_clear_log") {
            state.processManager.ClearLogs();
            if (state.host) {
                state.lastLogs.clear();
                state.host->SetElementText("txt_console", L"");
                state.host->SetElementText("txt_overview_log", L"");
                state.host->ScrollToBottom("scroll_console", true);
                state.host->ScrollToBottom("scroll_overview_log", true);
            }
        } else if (actionId == "action_copy_log") {
            std::wstring logs = state.processManager.GetRecentLogs(500);
            HWND parentHwnd = state.host ? state.host->GetHwnd() : nullptr;
            CopyTextToClipboard(parentHwnd, logs);
            state.processManager.AddLog(L"[管理中心] 运行日志已成功复制到系统剪切板。");
            UpdateUIStatus(state);
        } else if (actionId == "nav_overview") {
            SetActiveTab(state, 0);
        } else if (actionId == "nav_fleet") {
            SetActiveTab(state, 1);
            UpdateSceneAndFleetLabels(state);
        } else if (actionId == "nav_network") {
            SetActiveTab(state, 2);
        } else if (actionId == "nav_console") {
            SetActiveTab(state, 3);
        } else if (actionId == "action_set_scene_pads") {
            state.scene = L"pads";
            state.processManager.AddLog(L"[管理中心] 切换仿真场景为: 挑战卡模式 (pads)");
            UpdateSceneAndFleetLabels(state);
            UpdateUIStatus(state);
        } else if (actionId == "action_set_scene_room") {
            state.scene = L"room";
            state.processManager.AddLog(L"[管理中心] 切换仿真场景为: 室内房间 (room)");
            UpdateSceneAndFleetLabels(state);
            UpdateUIStatus(state);
        } else if (actionId == "action_set_scene_rings") {
            state.scene = L"rings";
            state.processManager.AddLog(L"[管理中心] 切换仿真场景为: 穿环竞技赛道 (rings)");
            UpdateSceneAndFleetLabels(state);
            UpdateUIStatus(state);
        } else if (actionId == "action_set_scene_forest") {
            state.scene = L"forest";
            state.processManager.AddLog(L"[管理中心] 切换仿真场景为: 室外树林 (forest)");
            UpdateSceneAndFleetLabels(state);
            UpdateUIStatus(state);
        } else if (actionId == "action_set_drones_1") {
            state.drones = 1;
            state.processManager.AddLog(L"[管理中心] 设置无人机仿真规模为: 单机 (1 台)");
            UpdateSceneAndFleetLabels(state);
            UpdateUIStatus(state);
        } else if (actionId == "action_set_drones_2") {
            state.drones = 2;
            state.processManager.AddLog(L"[管理中心] 设置无人机仿真规模为: 双机编队 (2 台)");
            UpdateSceneAndFleetLabels(state);
            UpdateUIStatus(state);
        } else if (actionId == "action_set_drones_4") {
            state.drones = 4;
            state.processManager.AddLog(L"[管理中心] 设置无人机仿真规模为: 四机编队 (4 台)");
            UpdateSceneAndFleetLabels(state);
            UpdateUIStatus(state);
        }
    }
}

void UpdateUIStatus(AppState& state) {
    if (!state.host) return;

    bool running = state.processManager.IsRunning();

    // 1. 运行状态徽章
    std::wstring currentStatus = running ? L"运行中 | UDP 8889 | 3D: 8080" : L"已停止 | UDP 8889 | 3D: 8080";
    if (currentStatus != state.lastStatus) {
        state.lastStatus = currentStatus;
        state.host->SetElementText("lbl_status", currentStatus.c_str());
        if (running) {
            // 运行中：翡翠绿指示灯，文字明亮淡绿
            state.host->SetElementBackground("indicator_dot", 0xFF10B981);
            state.host->SetElementForeground("lbl_status", 0xFF34D399);
        } else {
            // 已停止：中性板岩灰指示灯，文字柔和灰
            state.host->SetElementBackground("indicator_dot", 0xFF64748B);
            state.host->SetElementForeground("lbl_status", 0xFF94A3B8);
        }
    }

    // 2. Mind+ 连接状态
    std::wstring currentMindplus = running ? L"已就绪 (192.168.10.1)" : L"待启动 (192.168.10.1)";
    if (currentMindplus != state.lastMindplus) {
        state.lastMindplus = currentMindplus;
        state.host->SetElementText("lbl_mindplus_status", currentMindplus.c_str());
        state.host->SetElementForeground("lbl_mindplus_status", running ? 0xFF10B981 : 0xFF0A84FF);
    }

    // 3. 运行时长
    std::wstring currentUptime = FormatTime(state.processManager.GetUptimeSeconds());
    if (currentUptime != state.lastUptime) {
        state.lastUptime = currentUptime;
        state.host->SetElementText("lbl_uptime", currentUptime.c_str());
    }

    // 4. 网络环境诊断
    std::wstring currentNet = rmtt::NetworkDetector::GetStatusDescription();
    if (currentNet != state.lastNetStatus) {
        state.lastNetStatus = currentNet;
        state.host->SetElementText("lbl_net_status", currentNet.c_str());
        bool has10_1 = (currentNet.find(L"192.168.10.1") != std::wstring::npos);
        state.host->SetElementText("lbl_net_ip1_status", has10_1 ? L"已配置 (虚拟 IP 就绪)" : L"未检测到此 IP");
        state.host->SetElementText("lbl_net_ip2_status", has10_1 ? L"已配置 (网段可路由)" : L"未检测到此 IP");
    }

    // 5. 实时日志更新 (同时更新总览速览区与专有控制台)
    std::wstring logs = state.processManager.GetRecentLogs(200);
    if (!logs.empty() && logs != state.lastLogs) {
        state.lastLogs = logs;
        state.host->SetElementText("txt_console", logs.c_str());
        state.host->SetElementText("txt_overview_log", logs.c_str());
        state.host->ScrollToBottom("scroll_console");
        state.host->ScrollToBottom("scroll_overview_log");
    }
}

void OnAction(const char* actionId, void* userData) {
    auto state = static_cast<AppState*>(userData);
    if (!actionId || !state) return;

    // 安全排队，避免在 Direct2D 布局遍历/点击派发栈内重入修改 UI 树
    std::lock_guard<std::mutex> lock(state->actionMutex);
    state->pendingActions.push_back(actionId);
}

} // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int cmdShow) {
    ai_win_ui::InitializeProcessDpiAwareness();

    g_appState.instance = instance;
    g_appState.moduleDir = GetModuleDir();
    g_appState.projectRoot = FindProjectRoot(g_appState.moduleDir);

    ai_win_ui::HostCreateInfo info{};
    info.showCommand = cmdShow;
    info.chrome = L"custom";
    info.layoutPath = L"layouts/manager.xml";
    info.size = L"1120x720";
    info.onAction = OnAction;
    info.actionUser = &g_appState;

    auto host = ai_win_ui::Host::Create(instance, info);
    if (!host) {
        MessageBoxW(nullptr, L"无法初始化桌面原生管理中心界面 (Host::Create 失败)。", L"错误", MB_ICONERROR);
        return -1;
    }

    g_appState.host = host.get();

    // 设置窗口与任务栏图标
    HICON hIconBig = static_cast<HICON>(LoadImageW(instance, MAKEINTRESOURCEW(IDI_APPICON), IMAGE_ICON, 32, 32, LR_DEFAULTCOLOR));
    HICON hIconSmall = static_cast<HICON>(LoadImageW(instance, MAKEINTRESOURCEW(IDI_APPICON), IMAGE_ICON, 16, 16, LR_DEFAULTCOLOR));
    if (hIconBig) {
        SendMessageW(host->GetHwnd(), WM_SETICON, ICON_BIG, reinterpret_cast<LPARAM>(hIconBig));
    }
    if (hIconSmall) {
        SendMessageW(host->GetHwnd(), WM_SETICON, ICON_SMALL, reinterpret_cast<LPARAM>(hIconSmall));
    }

    // 初始设置 Tab 与状态
    SetActiveTab(g_appState, 0);
    UpdateSceneAndFleetLabels(g_appState);
    UpdateUIStatus(g_appState);

    // 设置定时器 (每 200ms 执行排队动作并更新状态与日志)
    SetTimer(host->GetHwnd(), 1001, 200, [](HWND, UINT, UINT_PTR, DWORD) {
        DrainPendingActions(g_appState);
        UpdateUIStatus(g_appState);
    });

    int exitCode = host->Run();

    // 退出前优雅停止后台 Python 引擎
    g_appState.processManager.Stop();

    return exitCode;
}
