@echo off
cls
title Study Timer Packager

echo ====================================
echo   Study Timer GUI
echo ====================================
echo.

REM --- 步骤 1: 清理旧的构建目录 ---
echo [1/4] Cleaning up old directories (build, dist)...

if exist "build" (
    echo    - Deleting 'build' directory...
    rmdir /s /q "build"
)
if exist "dist" (
    echo    - Deleting 'dist' directory...
    rmdir /s /q "dist"
)

REM --- 移除特定的文件 ---
if exist "study_log.csv" (
    echo    - Deleting specific file 'study_log.csv'...
    del /q "study_log.csv"
)

if exist "study_log.csv" (
    echo.
    echo [ERROR] 无法删除 'study_log.csv' 文件!
    echo 它可能被其他程序占用。请关闭后重试。
    echo.
    pause
    exit /b 1
)

if exist "config.json" (
    echo    - Deleting specific file 'config.json'...
    del /q "config.json"
)

if exist "config.json" (
    echo.
    echo [ERROR] 无法删除 'config.json' 文件!
    echo 它可能被其他程序占用。请关闭后重试。
    echo.
    pause
    exit /b 1
)

REM 检查是否真的删除成功了
if exist "build" (
    echo.
    echo [ERROR] 无法删除 'build' 文件夹!
    echo 它可能被其他程序占用 (例如文件浏览器或命令行窗口).
    echo 请关闭相关程序后重试。
    echo.
    pause
    exit /b 1
)
if exist "dist" (
    echo.
    echo [ERROR] 无法删除 'dist' 文件夹!
    echo 它可能被其他程序占用。请关闭后重试。
    echo.
    pause
    exit /b 1
)

echo    - Cleanup successful.
echo.

pause