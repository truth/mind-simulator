cmake_minimum_required(VERSION 3.20)
project(RoboMasterTTManager LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_compile_definitions(WIN32_LEAN_AND_MEAN NOMINMAX)

set(AI_WIN_UI_DIR "F:/AI-Projects/ai-win-ui" CACHE PATH "Path to ai-win-ui project")

add_executable(RoboMasterTT-Manager WIN32
    src/main.cpp
    src/process_manager.cpp
    src/network_detector.cpp
    src/app.rc
)

target_include_directories(RoboMasterTT-Manager PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${AI_WIN_UI_DIR}/include
    ${AI_WIN_UI_DIR}/src
)

if(MSVC)
    target_compile_options(RoboMasterTT-Manager PRIVATE /utf-8 /wd4819 /permissive-)
    set_property(TARGET RoboMasterTT-Manager PROPERTY
        MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
    target_link_options(RoboMasterTT-Manager PRIVATE
        "/alternatename:inflate=Cr_z_inflate"
        "/alternatename:inflateEnd=Cr_z_inflateEnd"
        "/alternatename:inflateInit2_=Cr_z_inflateInit2_"
        "/alternatename:inflateReset=Cr_z_inflateReset"
    )
endif()

set(YOGA_LIB_RELEASE "${AI_WIN_UI_DIR}/third_party/yoga-3.2.1/build-staticcrt/yoga/Release/yogacore.lib")
if(NOT EXISTS "${YOGA_LIB_RELEASE}")
    set(YOGA_LIB_RELEASE "${AI_WIN_UI_DIR}/third_party/yoga-3.2.1/build/yoga/Release/yogacore.lib")
endif()

set(YOGA_LIB_DEBUG "${AI_WIN_UI_DIR}/third_party/yoga-3.2.1/build-staticcrt/yoga/Debug/yogacore.lib")
if(NOT EXISTS "${YOGA_LIB_DEBUG}")
    set(YOGA_LIB_DEBUG "${AI_WIN_UI_DIR}/third_party/yoga-3.2.1/build/yoga/Debug/yogacore.lib")
endif()

set(AI_WIN_UI_LIB_RELEASE "${AI_WIN_UI_DIR}/build/Release/ai_win_ui_lib.lib")
set(AI_WIN_UI_LIB_DEBUG   "${AI_WIN_UI_DIR}/build/Debug/ai_win_ui_lib.lib")

set(SKIA_OUT_DIR "${AI_WIN_UI_DIR}/third_party/skia-m124/out")
file(GLOB SKIA_LIBS_REL LIST_DIRECTORIES false "${SKIA_OUT_DIR}/Release-x64/*.lib")
file(GLOB SKIA_LIBS_DBG LIST_DIRECTORIES false "${SKIA_OUT_DIR}/Debug-x64/*.lib")

target_link_libraries(RoboMasterTT-Manager PRIVATE
    $<$<CONFIG:Debug>:${AI_WIN_UI_LIB_DEBUG}>
    $<$<NOT:$<CONFIG:Debug>>:${AI_WIN_UI_LIB_RELEASE}>
    $<$<CONFIG:Debug>:${YOGA_LIB_DEBUG}>
    $<$<NOT:$<CONFIG:Debug>>:${YOGA_LIB_RELEASE}>
    $<$<CONFIG:Debug>:${SKIA_LIBS_DBG}>
    $<$<NOT:$<CONFIG:Debug>>:${SKIA_LIBS_REL}>
    opengl32
    d2d1
    dwrite
    dwmapi
    imm32
    windowscodecs
    ole32
    shell32
    uiautomationcore
    shlwapi
    iphlpapi
    ws2_32
)

# 编译后自动拷贝 resource 资源目录至 exe 旁边
add_custom_command(TARGET RoboMasterTT-Manager POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory
        "${CMAKE_CURRENT_SOURCE_DIR}/resource"
        "$<TARGET_FILE_DIR:RoboMasterTT-Manager>/resource"
    COMMENT "Copying app resources next to executable"
)
