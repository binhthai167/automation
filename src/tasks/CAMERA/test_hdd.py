import requests
from requests.auth import HTTPDigestAuth

url = "http://160.20.120.155/ISAPI/System/deviceInfo"
user = "admin"
pwd = "TDK-2025" # <-- Nhớ điền đúng pass của FC

try:
    print(f"Đang kết nối tới FC: {url}...")
    response = requests.get(url, auth=HTTPDigestAuth(user, pwd), timeout=5)
    print(f"Mã trạng thái: {response.status_code}")
    
    if response.status_code == 200:
        print("=> NGON LÀNH! FC đã mở API, script tổng sẽ chạy được.")
    elif response.status_code == 401:
        print("=> LỖI 401: Sai mật khẩu hoặc FC đang bị khóa bảo mật!")
    else:
        print(f"=> Lỗi khác: {response.text}")
        
except requests.exceptions.Timeout:
    print("=> TIMEOUT: Không thể kết nối. Đầu ghi bị tắt ISAPI, sai Cổng Web, hoặc máy tính đang bị Ban IP.")
except Exception as e:
    print(f"=> LỖI HỆ THỐNG: {e}")