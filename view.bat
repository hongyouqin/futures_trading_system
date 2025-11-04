@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM 设置eval_excel_name变量
if not "%~1"=="" (
    set "symbol=%~1"
) else (
    echo symbol is empty
    pause
    exit /b 1
)

python .\indicator_view.py --symbol "%symbol%" --period daily
python .\indicator_view.py --symbol "%symbol%" --period weekly

echo 执行完毕
pause