@echo off
:: Lệnh này giúp cửa sổ CMD hiển thị đúng tiếng Việt có dấu
chcp 65001 >nul

echo ==========================================
echo 1. BẮT ĐẦU CHẠY BÁO CÁO MÁY CHỦ (SERVER iLO)
echo ==========================================
:: Bạn nhớ thay tên file "Server.py" thành tên file thực tế của bạn nhé
D:\Automation\venv\Scripts\python.exe "D:\Automation\src\tasks\ILO\iLO.py"

echo.
echo ==========================================
echo Đang đợi 5 giây để đóng gói Email và giải phóng CPU...
echo ==========================================
timeout /t 5 /nobreak >nul

echo.
echo ==========================================
echo 2. BẮT ĐẦU CHẠY BÁO CÁO CAMERA
echo ==========================================
D:\Automation\venv\Scripts\python.exe "D:\Automation\src\tasks\CAMERA\Camera.py"

echo.
echo ==========================================
echo HOÀN THÀNH TẤT CẢ TÁC VỤ! TỰ ĐỘNG ĐÓNG SAU 3 GIÂY...
echo ==========================================
timeout /t 3 >nul
exit