@echo off
REM NAOqi SDK 环境配置脚本（Windows）
REM 用途：配置 Python 2.7 环境以使用 NAOqi SDK
REM 使用方法：在启动推送器前运行此脚本

echo ============================================================
echo NAOqi SDK 环境配置
echo ============================================================
echo.

REM 设置 NAOqi SDK 路径（请根据实际路径修改）
set NAOQI_SDK_PATH=D:\pynaoqi-python2.7-2.8.6.23-win64-vs2015-20191127_152649

REM 检查 SDK 是否存在
if not exist "%NAOQI_SDK_PATH%\lib" (
    echo [ERROR] NAOqi SDK 未找到！
    echo [ERROR] 请修改此脚本中的 NAOQI_SDK_PATH 变量
    echo [ERROR] 当前路径: %NAOQI_SDK_PATH%
    pause
    exit /b 1
)

REM 配置 PYTHONPATH
set PYTHONPATH=%NAOQI_SDK_PATH%\lib;%PYTHONPATH%

REM 配置 PATH（包含 DLL）
set PATH=%NAOQI_SDK_PATH%\bin;%PATH%

echo [OK] NAOqi SDK 路径: %NAOQI_SDK_PATH%
echo [OK] PYTHONPATH 已配置
echo [OK] PATH 已配置
echo.

REM 测试导入
echo 测试 NAOqi 导入...
python -c "from naoqi import ALProxy; print('[OK] NAOqi 导入成功！')" 2>nul
if errorlevel 1 (
    echo [ERROR] NAOqi 导入失败！
    echo [ERROR] 请检查：
    echo [ERROR] 1. Python 2.7 是否已安装
    echo [ERROR] 2. NAOqi SDK 路径是否正确
    echo [ERROR] 3. 是否为 64 位 Python（SDK 为 64 位）
    pause
    exit /b 1
)

echo.
echo ============================================================
echo 环境配置完成！
echo ============================================================
echo.
echo 现在可以运行推送器：
echo   python asr_realtime_pusher.py --robot-ip 192.168.93.152
echo   python gaze_realtime_pusher.py --robot-ip 192.168.93.152
echo.
echo 注意：此环境配置仅在当前命令行窗口有效
echo       如需永久配置，请添加到系统环境变量
echo.
