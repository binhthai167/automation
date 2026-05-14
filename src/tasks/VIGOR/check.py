import socket
import re
import smtplib
from email.message import EmailMessage
import datetime
import os

# ================= CẤU HÌNH HỆ THỐNG =================
EMAIL_FROM = "ltbinh.h@gmail.com"
APP_PASSWORD = "vkge xbmp zrxe knde" # Mã 16 ký tự của Google
GMAIL_TO = [
    # "hai.tranviet@nidec.com",
    # "phu.truongvan@nidec.com",
    "binh.lethai@nidec.com",
]

SYSLOG_IP = "0.0.0.0" # Lắng nghe trên mọi IP của máy tính này
SYSLOG_PORT = 514     # Cổng mặc định của Syslog
# FILE_DANH_SACH = r"D:\Automation\src\tasks\VIGOR\danh_sach_mac.txt"
FILE_DANH_SACH = "list_mac.txt"
TU_KHOA_BO_QUA = ["iphone", "galaxy", "xiaomi", "oppo", "vivo", "huawei", "android", "ipad", "redmi", "realme"]
# =====================================================

# Biến lưu trữ các MAC lạ đã gửi mail để tránh spam sếp nhiều lần
cac_mac_da_canh_bao = set()

thoi_gian_file_sua_doi = 0
danh_sach_quen_cache = set()

def lay_danh_sach_quen():
    global thoi_gian_file_sua_doi, danh_sach_quen_cache
    try:
        # Nhìn đồng hồ xem file text vừa bị sửa lúc mấy giờ
        thoi_gian_hien_tai = os.path.getmtime(FILE_DANH_SACH)
        
        # Nếu thời gian bị lệch -> Có ai đó (bạn) vừa mở file text ra thêm/bớt MAC và bấm Save
        if thoi_gian_hien_tai != thoi_gian_file_sua_doi:
            mac_quen = set()
            with open(FILE_DANH_SACH, "r") as f:
                for line in f:
                    match = re.search(r'([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})', line)
                    if match:
                        mac_quen.add(match.group(1).lower())
            
            # Cập nhật lại bộ nhớ đệm
            danh_sach_quen_cache = mac_quen
            thoi_gian_file_sua_doi = thoi_gian_hien_tai
            print(f"[*] Phát hiện danh sách được cập nhật! Đã tải lại {len(mac_quen)} MAC vào bộ nhớ.")
            
    except FileNotFoundError:
        print(f"[-] Cảnh báo: Không tìm thấy file {FILE_DANH_SACH}")
        
    # Trả về danh sách MAC (nếu file không đổi thì nó trả về kết quả cũ rất nhanh)
    return danh_sach_quen_cache
 
def send_email(mac_la, ten_thiet_bi, thong_tin_log):
    """Hàm tự động gửi email cảnh báo"""
    thoi_gian = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    msg = EmailMessage()
    msg['Subject'] = f"🚨 CẢNH BÁO: Phát hiện thiết bị lạ bắt Wifi Visitor!"
    msg['From'] = EMAIL_FROM
    msg["To"] = ", ".join(GMAIL_TO)
    
    noi_dung = f"""
    Phát hiện một thiết bị Không có trong danh sách đang kết nối vào mạng Wifi.
    
    - Thời gian: {thoi_gian}
    - Tên thiết bị: {ten_thiet_bi}
    - Địa chỉ MAC thiết bị lạ: {mac_la.upper()}
    
    Chi tiết hệ thống lưu lại:
    {thong_tin_log}
    
    """
    msg.set_content(noi_dung)
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_FROM, APP_PASSWORD)
            smtp.send_message(msg)
        print(f"[+] ĐÃ GỬI MAIL CẢNH BÁO THÀNH CÔNG CHO MAC: {ten_thiet_bi}, {mac_la}")
    except Exception as e:
        print(f"[-] Lỗi gửi mail: {e}")

def bat_dau_giam_sat():
    """Hàm chính để mở trạm thu Syslog và phân tích"""
    print(f"[*] Đang lắng nghe tín hiệu từ Router DrayTek ở cổng {SYSLOG_PORT}...\n")
    
    # Mở cổng UDP để hứng Log
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((SYSLOG_IP, SYSLOG_PORT))
    
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            log_text = data.decode('utf-8', errors='ignore')
            
            # Chỉ bắt các log có liên quan đến việc cấp phát IP (DHCP)
            if "DHCP" in log_text or "Lease" in log_text or "ARP" in log_text:
                # Dò tìm địa chỉ MAC trong dòng Log
                mac_match = re.search(r'([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})', log_text)
                
                if mac_match:
                    mac_hien_tai = mac_match.group(1).lower()
                    danh_sach_quen = lay_danh_sach_quen()
                    # Nếu MAC này không nằm trong file txt và chưa bị gửi mail cảnh báo
                    # Nếu MAC này không nằm trong file txt và chưa bị xử lý
                    if mac_hien_tai not in danh_sach_quen and mac_hien_tai not in cac_mac_da_canh_bao:
                        ten_match = re.search(r'\((.*?)\)', log_text)
                        # Lấy tên, nếu không có thì gán là rỗng ("")
                        ten_thiet_bi = ten_match.group(1).strip() if ten_match else ""
                        
                        # Ghi nhận MAC này đã được xử lý (dù gửi mail hay bỏ qua) để không lặp lại liên tục
                        cac_mac_da_canh_bao.add(mac_hien_tai)

                        # BỘ LỌC 1: Bỏ qua thiết bị không có tên
                        if not ten_thiet_bi:
                            print(f"[*] Đã chặn báo cáo: MAC {mac_hien_tai} (Lý do: Không có tên)")
                            continue # Dừng lại, không chạy các lệnh bên dưới nữa
                            
                        # BỘ LỌC 2: Bỏ qua thiết bị di động
                        ten_thiet_bi_lower = ten_thiet_bi.lower()
                        # Hàm any() sẽ duyệt xem có từ khóa nào nằm trong tên thiết bị không
                        la_di_dong = any(tu_khoa in ten_thiet_bi_lower for tu_khoa in TU_KHOA_BO_QUA)
                        
                        if la_di_dong:
                            print(f"[*] Đã chặn báo cáo: MAC {mac_hien_tai} - Tên: {ten_thiet_bi} (Lý do: Là thiết bị di động)")
                            continue
                            
                        # === VƯỢT QUA BỘ LỌC ===
                        # Nếu tới được đây tức là có tên và không phải điện thoại
                        print(f"[!] PHÁT HIỆN PC/LAPTOP LẠ: {ten_thiet_bi} - MAC: {mac_hien_tai}")
                        send_email(mac_hien_tai, ten_thiet_bi, log_text)
                        
        except KeyboardInterrupt:
            print("\n[*] Đã dừng hệ thống giám sát.")
            break
        except Exception as e:
            print(f"[-] Có lỗi xảy ra trong lúc nghe Log: {e}")

if __name__ == "__main__":
    bat_dau_giam_sat()