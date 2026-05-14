import os
import requests
from requests.auth import HTTPDigestAuth
from datetime import datetime

class CCTVDownloader:
    @staticmethod
    def download_dahua(ip, username, password, channel, start_time, end_time, output_path):
        st_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        et_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Link API Dahua (Kênh giữ nguyên số khách nhập)
        url = f"http://{ip}/cgi-bin/loadfile.cgi?action=startLoad&channel={channel}&startTime={st_str}&endTime={et_str}"
        
        print(f"\n⏳ Đang kết nối NVR Dahua tải kênh {channel} từ {st_str} đến {et_str}...")
        try:
            response = requests.get(url, auth=HTTPDigestAuth(username, password), stream=True, timeout=15)
            if response.status_code == 200:
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024*1024): # Tải từng cục 1MB
                        if chunk: f.write(chunk)
                print(f"✅ THÀNH CÔNG! Đã tải xong video: {output_path}")
            else:
                print(f"❌ LỖI: Dahua từ chối cấp file (Mã lỗi {response.status_code})")
        except Exception as e:
            print(f"❌ LỖI MẠNG: {e}")

    @staticmethod
    def download_hikvision(ip, username, password, channel, start_time, end_time, output_path):
        st_str = start_time.strftime("%Y%m%dT%H%M%SZ")
        et_str = end_time.strftime("%Y%m%dT%H%M%SZ")
        url = f"http://{ip}/ISAPI/ContentMgmt/download"
        
        # Cố gắng tải luồng chính (01) của Analog (đầu 1) hoặc IP Cam (đầu 33)
        channels_to_try = [f"{channel}01", f"{int(channel)+32}01"]
        
        print(f"\n⏳ Đang kết nối NVR Hikvision tải kênh {channel}...")
        for chan_id in channels_to_try:
            xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
            <downloadRequest>
                <playbackURI>rtsp://{ip}/Streaming/tracks/{chan_id}/?starttime={st_str}&amp;endtime={et_str}</playbackURI>
            </downloadRequest>"""
            
            try:
                response = requests.post(url, auth=HTTPDigestAuth(username, password), data=xml_payload, stream=True, timeout=15)
                if response.status_code == 200:
                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=1024*1024):
                            if chunk: f.write(chunk)
                    print(f"✅ THÀNH CÔNG! Đã tải xong video: {output_path}")
                    return # Thành công thì thoát luôn
                elif response.status_code == 401:
                    print("❌ LỖI: Sai mật khẩu!")
                    return
            except Exception as e:
                print(f"❌ LỖI MẠNG: {e}")
                return
                
        print("❌ LỖI: Không tìm thấy dữ liệu video ở khoảng thời gian này hoặc kênh không tồn tại.")

def main():
    print("=============================================")
    print("   CÔNG CỤ TRÍCH XUẤT VIDEO CAMERA NHANH")
    print("=============================================")
    
    # 1. Chọn hãng
    print("Chọn hãng Camera:")
    print("1. Dahua")
    print("2. Hikvision")
    choice = input("Nhập số (1 hoặc 2): ").strip()
    if choice not in ['1', '2']:
        print("Lựa chọn không hợp lệ!")
        return
        
    # 2. Nhập thông tin thiết bị
# 2. Nhập thông tin thiết bị
    ip_input = input("\nNhập IP đầu ghi (VD: 160.20.120.155): ").strip()
    
    # Tự động dọn dẹp nếu người dùng dán thừa http:// hoặc https://
    ip = ip_input.replace("http://", "").replace("https://", "").split("/")[0]
    
    user = input("Nhập Username (Mặc định: admin): ").strip() or "admin"
    pwd = input("Nhập Password: ").strip()
    channel = input("Nhập số thứ tự Kênh Camera (VD: 1): ").strip()
    
    # 3. Nhập thời gian
    print("\n--- Nhập khoảng thời gian cần xem lại ---")
    print("(Định dạng bắt buộc: YYYY-MM-DD HH:MM:SS)")
    start_str = input("Từ lúc (VD: 2026-04-07 08:00:00): ").strip()
    end_str = input("Đến lúc (VD: 2026-04-07 08:15:00): ").strip()
    
    try:
        start_time = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        print("\n❌ LỖI: Bạn nhập sai định dạng thời gian rồi. Phải chuẩn xác dạng YYYY-MM-DD HH:MM:SS nhé!")
        return
        
    # Tính toán tên file đầu ra cho chuyên nghiệp
    safe_st = start_time.strftime("%Y%m%d_%H%M")
    safe_et = end_time.strftime("%H%M")
    hang = "Dahua" if choice == '1' else "Hikvision"
    
    # Lưu file ra màn hình Desktop cho dễ tìm (Bạn có thể đổi đường dẫn)
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
    output_filename = f"{hang}_Cam{channel}_{safe_st}_den_{safe_et}.mp4"
    output_path = os.path.join(desktop_path, output_filename)
    
    # 4. Thực thi tải
    if choice == '1':
        CCTVDownloader.download_dahua(ip, user, pwd, channel, start_time, end_time, output_path)
    else:
        CCTVDownloader.download_hikvision(ip, user, pwd, channel, start_time, end_time, output_path)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nĐã hủy thao tác.")