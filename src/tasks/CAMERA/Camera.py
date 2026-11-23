import json
import requests
import re
import base64
import os
import argparse
import smtplib
import time
from datetime import datetime
from typing import Dict, Tuple
from requests.auth import HTTPDigestAuth
from openai import OpenAI
import openpyxl
from openpyxl.drawing.image import Image
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import cv2
import numpy as np
from datetime import datetime, timedelta
import calendar

# Thresholds (tune as needed)
DARK_THRESHOLD = 35              # pixel value below this is considered dark
DARK_PIXEL_RATIO = 0.98         # fraction of dark pixels to consider frame black
WHITE_THRESHOLD = 245           # mean above this -> white frame
STRIPE_VARIATION_RATIO = 0.995   # ratio of stddev of row/col sums to mean -> stripe
NOISE_LAPLACIAN_THRESH = 200     # minimal laplacian magnitude to count as high-frequency noise
NOISE_PIXEL_RATIO = 0.15           # fraction of pixels above NOISE_LAPLACIAN_THRESH to consider noisy

NG_CAMERAS = []
SYSTEM_ALERTS = []
ALL_HDD_STATUS = []
RETENTION_ALERTS = [] # Danh sách các camera lưu < 365 ngày
ALL_CAMERA_RETENTION = []

GMAIL_USER = "noreply.nivs@gmail.com"
GMAIL_APP_PASSWORD = "jjxpgndrikbftwed" 
GMAIL_TO = [
    "hai.tranviet@nidec.com",
    "phu.truongvan@nidec.com",
    "binh.lethai@nidec.com",
]

def is_black(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    dark_ratio = np.count_nonzero(gray < DARK_THRESHOLD) / gray.size
    return dark_ratio >= DARK_PIXEL_RATIO

def is_white(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return np.mean(gray) > WHITE_THRESHOLD

def is_horizontal_stripe(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    row_sums = gray.sum(axis=1).astype(np.float32)
    return (np.std(row_sums) / (np.mean(row_sums) + 1e-6)) > STRIPE_VARIATION_RATIO

def is_vertical_stripe(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    col_sums = gray.sum(axis=0).astype(np.float32)
    return (np.std(col_sums) / (np.mean(col_sums) + 1e-6)) > STRIPE_VARIATION_RATIO

def is_noisy(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    high_freq = np.abs(lap) > NOISE_LAPLACIAN_THRESH
    ratio = np.count_nonzero(high_freq) / high_freq.size
    return ratio > NOISE_PIXEL_RATIO

# ======================
# OVERLAY TEXT DETECTION (timestamp, camera label)
# ======================
def has_overlay_text(gray):
    h, w = gray.shape

    # vùng nghi ngờ có timestamp / camera name
    bottom = gray[int(h*0.80):, :]
    top = gray[:int(h*0.15), :]

    # detect edges
    edges_bottom = cv2.Canny(bottom, 30, 90)
    edges_top = cv2.Canny(top, 30, 90)

    # nếu vùng này có edge ratio cao => có text overlay
    if np.count_nonzero(edges_bottom) / edges_bottom.size > 0.002:
        return True
    if np.count_nonzero(edges_top) / edges_top.size > 0.002:
        return True

    return False

# DARK FRAME DETECTOR (has overlay)
# ======================
def is_black_or_no_detail(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean_val = np.mean(gray)

    # Khung hình đen thật
    if mean_val < 10:
        return True

    lap = cv2.Laplacian(gray, cv2.CV_64F)
    sharpness = np.mean(np.abs(lap))

    # camera thật chỉ coi là 'no detail' khi <1.0
    return sharpness < 1.0

def has_structure(gray):
    h, w = gray.shape
    
    # tránh vùng chứa overlay text
    crop = gray[int(h*0.20):int(h*0.80), :]

    mean_val = np.mean(crop)
    if mean_val < 50:
        return False

    lap = cv2.Laplacian(crop, cv2.CV_64F)
    sharpness = np.mean(np.abs(lap))
    if sharpness < 2.0:
        return False

    edges = cv2.Canny(crop, 40, 120)
    ratio = np.count_nonzero(edges) / edges.size

    return ratio > 0.02

def is_too_dark(gray):
    return np.mean(gray) < 20      # NG ngay nếu ảnh tối toàn cục

def classify_image(path):
    img = cv2.imread(path)
    if img is None:
        return {"error": True, "description": "Lỗi: Không thể đọc file ảnh"}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if is_too_dark(gray): return {"error": True, "description": "Ảnh đen sì"}
    if is_black(img): return {"error": True, "description": "Ảnh đen (Black)"}
    if is_white(img): return {"error": True, "description": "Ảnh cháy sáng (White)"}
    if is_horizontal_stripe(img): return {"error": True, "description": "Sọc ngang (Horizontal stripe)"}
    if is_vertical_stripe(img): return {"error": True, "description": "Sọc dọc (Vertical stripe)"}
    if is_noisy(img): return {"error": True, "description": "Nhiễu hạt mạnh (Noisy)"}
    if is_black_or_no_detail(img): return {"error": True, "description": "Mờ / Mất chi tiết (No detail)"}

    return {"error": False, "description": "OK"}


class CameraUtility:
    """Xử lý giao tiếp với camera hãng DAHUA"""
    @staticmethod
    def get_snapshot(base_url, username, password, channel_id, output_path, max_retries=2):
        url = f"{base_url}/cgi-bin/snapshot.cgi?channel={channel_id+1}"
        
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=10)
                if response.status_code == 200:
                    with open(output_path, "wb") as f:
                        f.write(response.content)
                    return True
            except Exception:
                pass
                
            if attempt < max_retries:
                time.sleep(2)
                
        return False

    @staticmethod
    def get_channel_title_config(base_url, username, password):
        url = f"{base_url}/cgi-bin/configManager.cgi?action=getConfig&name=ChannelTitle"
        try:
            response = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=10)
            if response.status_code == 200:
                data = response.text
                pattern = r"table\.ChannelTitle\[(\d+)\]\.Name=([^\n]+)"
                matches = re.findall(pattern, data)
                return {int(channel_id): name.strip() for channel_id, name in matches}
        except: pass
        return {}

    @staticmethod
    def get_hdd_status(base_url, username, password):
        url = f"{base_url}/cgi-bin/storageDevice.cgi?action=getDeviceAllInfo"
        try:
            response = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=10)
            if response.status_code != 200 or "ErrorID" in response.text:
                return "Không hỗ trợ đọc HDD", False
                
            data = response.text
            # KIỂU 1
            indices_v1 = re.findall(r"table\.StorageDevice\[(\d+)\]", data)
            if indices_v1:
                max_idx = max([int(i) for i in indices_v1])
                results, has_error = [], False
                for i in range(max_idx + 1):
                    status_match = re.search(fr"StorageDevice\[{i}\]\.Status=(\w+)", data)
                    capacity_match = re.search(fr"StorageDevice\[{i}\]\.TotalBytes=(\d+)", data)
                    status = status_match.group(1) if status_match else "Unknown"
                    total_bytes = int(capacity_match.group(1)) if capacity_match else 0
                    total_tb = round(total_bytes / (1024**4), 2)
                    results.append(f"SATA-{i+1}: {status} ({total_tb}TB)")
                    if status not in ["Normal", "Active", "B.thường"]:
                        has_error = True
                return " | ".join(results), has_error

            # KIỂU 2
            indices_v2 = set(re.findall(r"list\.info\[(\d+)\]\.State", data))
            if indices_v2:
                results, has_error = [], False
                for idx in sorted(list(indices_v2)):
                    state_match = re.search(fr"list\.info\[{idx}\]\.State=(\w+)", data)
                    state = state_match.group(1) if state_match else "Unknown"
                    bytes_matches = re.findall(fr"list\.info\[{idx}\]\.Detail\[\d+\]\.TotalBytes=([\d\.]+)", data)
                    total_bytes = sum(float(b) for b in bytes_matches)
                    total_tb = round(total_bytes / (1024**4), 2) 
                    error_matches = re.findall(fr"list\.info\[{idx}\]\.Detail\[\d+\]\.IsError=(true)", data, re.IGNORECASE)
                    
                    if state != "Success" or error_matches:
                        has_error, status_text = True, "LỖI"
                    else:
                        status_text = "Bình thường"
                    results.append(f"Disk-{int(idx)+1}: {status_text} ({total_tb}TB)")
                return " | ".join(results), has_error

            return "Không có dữ liệu ổ cứng (No Disk)", True
        except Exception as e:
            return f"Lỗi lấy thông tin: {str(e)}", True

    @staticmethod
    def get_system_info(base_url, username, password):
        url = f"{base_url}/cgi-bin/magicBox.cgi?action=getSystemInfo"
        try:
            response = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=10)
            if response.status_code == 200:
                ver = re.search(r"Version=([^\n]+)", response.text)
                return f"Online (Firmware: {ver.group(1).strip() if ver else 'N/A'})"
        except: pass
        return "Offline/Lỗi kết nối"
    
    @staticmethod
    def get_oldest_record_days(base_url, username, password, channel_id):
        """Tìm ngày lưu cũ nhất bằng cơ chế Kiểm tra chéo (Gọng kìm 2 chiều)"""
        now = datetime.now()
        session = requests.Session()
        session.auth = HTTPDigestAuth(username, password)
        
        def check_month_data(months_back):
            target_date = now - timedelta(days=30 * months_back)
            year = target_date.year
            month = target_date.month
            last_day = calendar.monthrange(year, month)[1] 
            
            start_time = f"{year}-{month:02d}-01%2000:00:00"
            end_time = f"{year}-{month:02d}-{last_day}%2023:59:59"
            
            found = False
            d_str = "N/A"
            days = 0
            
            try:
                # BƯỚC 1: Xin phiên
                create_url = f"{base_url}/cgi-bin/mediaFileFind.cgi?action=factory.create"
                res_create = session.get(create_url, timeout=5)
                match_obj = re.search(r'result=(\d+)', res_create.text)
                if not match_obj:
                    return False, "N/A", 0
                object_id = match_obj.group(1) 

                # BƯỚC 2: Tìm file
                find_url = (
                    f"{base_url}/cgi-bin/mediaFileFind.cgi?"
                    f"action=findFile&object={object_id}&"
                    f"condition.Channel={channel_id}&"
                    f"condition.StartTime={start_time}&"
                    f"condition.EndTime={end_time}&"
                    f"condition.Types[0]=dav&"
                    f"condition.Flag[0]=*"
                )
                req = requests.Request('GET', find_url)
                prep = session.prepare_request(req)
                prep.url = find_url  
                res_find = session.send(prep, timeout=5)

                # BƯỚC 3: Bóc kết quả
                if res_find.status_code == 200 and "OK" in res_find.text:
                    res_next = session.get(f"{base_url}/cgi-bin/mediaFileFind.cgi?action=findNextFile&object={object_id}&count=1", timeout=5)
                    if "StartTime=" in res_next.text:
                        match_time = re.search(r'StartTime=(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', res_next.text)
                        if match_time:
                            d_str = match_time.group(1)
                            old_dt = datetime.strptime(d_str, "%Y-%m-%d %H:%M:%S")
                            days = (now - old_dt).days
                            found = True

                # Hủy phiên
                session.get(f"{base_url}/cgi-bin/mediaFileFind.cgi?action=factory.destroy&object={object_id}", timeout=5)
            except Exception:
                pass
            
            return found, d_str, days

        forward_date = "N/A"
        forward_days = 0
        for m in range(13, -1, -1):
            found, d_str, days = check_month_data(m)
            if found:
                forward_date = d_str
                forward_days = days
                break

        backward_date = "N/A"
        backward_days = 0
        for m in range(0, 14):
            found, d_str, days = check_month_data(m)
            if found:
                backward_date = d_str
                backward_days = days
            else:
                break

        if abs(forward_days - backward_days) <= 1:
            return forward_date, forward_days
        else:
            print(f"[!] LỆCH DỮ LIỆU KÊNH {channel_id}: Quét tiến {forward_days} ngày | Quét lùi {backward_days} ngày")
            warning_str = f"{forward_date} (LỆCH! Tiến: {forward_days} ngày | Lùi: {backward_days} ngày)"
            final_days = max(forward_days, backward_days)
            return warning_str, final_days
    

class HikvisionUtility:
    """Xử lý giao tiếp với camera hãng HIKVISION"""
    @staticmethod
    def get_snapshot(base_url, username, password, channel_id, output_path):
        ip_chan = channel_id + 32
        
        # --- CÁCH 1: DÙNG API ---
        urls_to_try = [
            f"{base_url}/ISAPI/Streaming/channels/{channel_id}02/picture",
            f"{base_url}/ISAPI/Streaming/channels/{channel_id}01/picture",
            f"{base_url}/ISAPI/Streaming/channels/{ip_chan}02/picture",
            f"{base_url}/ISAPI/Streaming/channels/{ip_chan}01/picture"
        ]
        for url in urls_to_try:
            try:
                response = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=5)
                if response.status_code == 200 and len(response.content) > 1000:
                    with open(output_path, "wb") as f:
                        f.write(response.content)
                    return True
            except: 
                continue

        # --- CÁCH 2: DÙNG RTSP ---
        ip_address = base_url.replace("http://", "").replace("https://", "").split(":")[0]
        rtsp_channels = [f"{channel_id}02", f"{channel_id}01", f"{ip_chan}02", f"{ip_chan}01"]
        
        for rtsp_chan in rtsp_channels:
            rtsp_url = f"rtsp://{username}:{password}@{ip_address}:554/Streaming/Channels/{rtsp_chan}"
            try:
                cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
                if cap.isOpened():
                    for _ in range(20):
                        ret, frame = cap.read()
                        if not ret:
                            break
                    if ret and frame is not None:
                        cv2.imwrite(output_path, frame)
                        cap.release()
                        return True
                cap.release()
            except Exception:
                continue
                
        return False

    @staticmethod
    def get_channel_title_config(base_url, username, password):
        channels = {}
        urls_to_try = [
            f"{base_url}/ISAPI/ContentMgmt/InputProxy/channels",
            f"{base_url}/ISAPI/System/Video/inputs/channels"
        ]
        
        for url in urls_to_try:
            try:
                response = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=10)
                if response.status_code == 200:
                    channel_blocks = re.findall(r'<(?:VideoInputChannel|InputProxyChannel)[^>]*>(.*?)</(?:VideoInputChannel|InputProxyChannel)>', response.text, re.DOTALL)
                    for block in channel_blocks:
                        c_id = re.search(r'<id>(\d+)</id>', block)
                        c_name = re.search(r'<name>(.*?)</name>', block)
                        if c_id and c_name:
                            channels[int(c_id.group(1))] = c_name.group(1).strip()
                    if channels:
                        return channels
            except: 
                pass
                
        print(f"[*] Không lấy được danh sách tên kênh API. Đang kích hoạt ép chụp ảnh thủ công...")
        for i in range(1, 17): 
            channels[i] = f"Camera {i:02d}"
            
        return channels

    @staticmethod
    def get_hdd_status(base_url, username, password):
        url = f"{base_url}/ISAPI/ContentMgmt/Storage"
        try:
            response = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=20)
            if response.status_code == 200:
                hdd_blocks = re.findall(r'<hdd[^>]*>(.*?)</hdd>', response.text, re.DOTALL)
                if not hdd_blocks:
                    return "Không tìm thấy ổ cứng (No Disk)", True

                results, has_error = [], False
                for i, block in enumerate(hdd_blocks):
                    status_match = re.search(r'<status>(.*?)</status>', block, re.IGNORECASE)
                    capacity_match = re.search(r'<capacity>(.*?)</capacity>', block, re.IGNORECASE)
                    
                    status = status_match.group(1) if status_match else "Unknown"
                    total_mb = int(capacity_match.group(1)) if capacity_match else 0
                    total_tb = round(total_mb / (1024**2), 2)
                    
                    if status.upper() not in ["OK", "NORMAL"]:
                        has_error, status_text = True, "LỖI"
                    else:
                        status_text = "B.thường"
                    results.append(f"Disk-{i+1}: {status_text} ({total_tb}TB)")
                return " | ".join(results), has_error
        except Exception as e:
            return f"Lỗi kết nối API HDD: {str(e)}", True
        return "N/A", False

    @staticmethod
    def get_system_info(base_url, username, password):
        url = f"{base_url}/ISAPI/System/deviceInfo"
        try:
            response = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=10)
            if response.status_code == 200:
                ver = re.search(r'<firmwareVersion>(.*?)</firmwareVersion>', response.text)
                return f"Online (Firmware: {ver.group(1).strip() if ver else 'N/A'})"
        except: pass
        return "Offline/Lỗi kết nối"
    

def send_alert_email():
    if not ALL_HDD_STATUS and not NG_CAMERAS:
        print("Không có dữ liệu hệ thống để gửi mail.")
        return

    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = ", ".join(GMAIL_TO)
    
    if NG_CAMERAS or SYSTEM_ALERTS or RETENTION_ALERTS:
        msg["Subject"] = f"🔴 [CẢNH BÁO] {len(SYSTEM_ALERTS)} NVR lỗi | {len(NG_CAMERAS)} Cam lỗi | {len(RETENTION_ALERTS)} Cam Hải Quan vi phạm thời gian lưu"
    else:
        msg["Subject"] = "🟢 [BÁO CÁO] Hệ thống Camera hoạt động tốt & Đạt chuẩn lưu trữ 365 ngày"

    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; color: #333; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
            th, td {{ border: 1px solid #dddddd; text-align: left; padding: 10px; font-size: 14px; }}
            th {{ background-color: #f4f4f4; color: #000; font-weight: bold; }}
            .status-ok {{ color: #008000; font-weight: bold; }}
            .status-ng {{ color: #d93025; font-weight: bold; }}
            .header-box {{ background-color: #004a99; color: white; padding: 15px; text-align: center; margin-bottom: 20px; }}
            h3 {{ color: #004a99; border-bottom: 2px solid #004a99; padding-bottom: 5px; display: inline-block; }}
        </style>
    </head>
    <body>
        <div class="header-box">
            <h2 style="margin: 0;">BÁO CÁO TỔNG HỢP HỆ THỐNG CAMERA</h2>
            <p style="margin: 5px 0 0 0;">Thời gian quét: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
        </div>

        <h3>1. TÌNH TRẠNG ĐẦU GHI & Ổ CỨNG (NVR / HDD)</h3>
        <table>
            <tr>
                <th width="5%">STT</th>
                <th width="20%">Khu vực / Xưởng</th>
                <th width="10%">Hãng</th>
                <th width="25%">Trạng thái Hệ thống</th>
                <th width="40%">Sức khỏe Ổ cứng (HDD)</th>
            </tr>
    """

    if ALL_HDD_STATUS:
        for i, hdd_str in enumerate(ALL_HDD_STATUS):
            match = re.match(r'\[(.*?)\]\s+\((.*?)\)\s+-\s+(.*?)\s+\|\s+HDD:\s+(.*)', hdd_str)
            if match:
                factory, brand, sys_info, hdd_info = match.groups()
            else:
                factory, brand, sys_info, hdd_info = "Unknown", "Unknown", hdd_str, "Unknown"

            hdd_class = "status-ng" if "LỖI" in hdd_info.upper() else "status-ok"
            sys_class = "status-ng" if "Offline" in sys_info else "status-ok"

            html_body += f"""   
                <tr>
                    <td align="center">{i+1}</td>
                    <td><b>{factory}</b></td>
                    <td align="center">{brand}</td>
                    <td class="{sys_class}">{sys_info}</td>
                    <td class="{hdd_class}">{hdd_info}</td>
                </tr>
            """
    else:
        html_body += """<tr><td colspan="5" align="center">Không có dữ liệu kiểm tra thiết bị.</td></tr>"""

    html_body += """
        </table>

        <h3>2. DANH SÁCH CAMERA MẤT HÌNH ẢNH (NG)</h3>
    """

    if NG_CAMERAS:
        html_body += """
        <table>
            <tr>
                <th width="5%">STT</th>
                <th width="25%">Xưởng / Vị trí</th>
                <th width="35%">Tên Camera (Kênh)</th>
                <th width="35%">Mô tả lỗi thuật toán AI</th>
            </tr>
        """
        for i, item in enumerate(NG_CAMERAS):
            html_body += f"""
                <tr>
                    <td align="center">{i+1}</td>
                    <td><b>{item.get('Xưởng', 'Unknown')}</b></td>
                    <td class="status-ng">{item.get('Kênh', 'Unknown')}</td>
                    <td>{item.get('reason', '')}</td>
                </tr>
            """
        html_body += """
        </table>
        <p style="color: #666; font-style: italic;">* Lưu ý: Đã đính kèm ảnh chụp các camera bị lỗi bên dưới email này để đối chiếu.</p>
        """
    else:
        html_body += """<p class="status-ok" style="font-size: 16px;">✅ Tuyệt vời! Tất cả camera đều hiển thị hình ảnh bình thường, không phát hiện nhiễu hay sọc đen.</p>"""

    html_body += """
        <h3>3. TÌNH TRẠNG LƯU TRỮ DỮ LIỆU Ở CAM HẢI QUAN (MỤC TIÊU: 365 NGÀY)</h3>
    """
    
    if ALL_CAMERA_RETENTION: 
        html_body += """
        <table>
            <tr>
                <th width="5%">STT</th>
                <th width="20%">Tên Xưởng</th> <th width="20%">Tên camera</th>
                <th width="25%">Thời điểm dữ liệu cũ nhất hiện còn lưu được</th>
                <th width="15%">Số ngày lưu thực tế hiện tại</th>
                <th width="15%">Đánh giá</th>
            </tr>
        """
        for i, item in enumerate(ALL_CAMERA_RETENTION):
            factory_name = item.get('Xưởng', 'Unknown')
            camera_name = item.get('Kênh', 'Unknown')
            oldest_date = item.get('Cũ nhất', 'Unknown')
            days_retained = item.get('Số ngày', 0)
            
            if days_retained >= 365:
                eval_text = "ĐẠT"
                eval_class = "status-ok"
            else:
                eval_text = "KHÔNG ĐẠT"
                eval_class = "status-ng"

            html_body += f"""
            <tr>
                <td align="center">{i+1}</td>
                <td><b>{factory_name}</b></td>
                <td><b>{camera_name}</b></td>
                <td align="center">{oldest_date}</td>
                <td align="center" class="{eval_class}"><b>{days_retained} ngày</b></td>
                <td align="center" class="{eval_class}"><b>{eval_text}</b></td>
            </tr>
            """
        html_body += "</table>"
    else:
        html_body += """<p>Không có dữ liệu lưu trữ của camera để hiển thị.</p>"""
    html_body += """
    </body>
    </html>
    """

    msg.attach(MIMEText(html_body, "html"))

    for item in NG_CAMERAS:
        if item.get('path') and os.path.exists(item['path']):
            try:
                with open(item["path"], "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(item['path'])}")
                msg.attach(part)
            except: pass

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, GMAIL_TO, msg.as_string())
        print("\n>>> Đã gửi email báo cáo!")
    except Exception as e:
        print(f"\n>>> Lỗi khi gửi email: {e}")

# =========================================================================
# HÀM SUY LUẬN NGUYÊN NHÂN & HƯỚNG KHẮC PHỤC (Dựa trên hiện tượng)
# =========================================================================
def get_cause_and_solution(error_desc):
    error = error_desc.lower()
    if "đen" in error or "black" in error:
        return "Mất hồng ngoại ban đêm, sụt nguồn cấp hoặc cảm biến ảnh lỗi", "Kiểm tra nguồn cấp 12V/PoE, vệ sinh ống kính, che chắn ánh sáng ngược"
    elif "sọc" in error or "stripe" in error or "nhiễu" in error or "noisy" in error:
        return "Nhiễu tín hiệu, cáp mạng kém chất lượng hoặc đầu bóp cáp lỏng", "Kiểm tra lại đường dây cáp, bấm lại đầu mạng RJ45, cách ly nguồn nhiễu điện"
    elif "mờ" in error or "chi tiết" in error:
        return "Ống kính bị bám bụi bẩn, đọng hơi nước sương mù", "Vệ sinh mặt kính bên ngoài bề mặt camera"
    elif "trắng" in error or "cháy sáng" in error or "white" in error:
        return "Ngược sáng cực mạnh hoặc lỗi cảm biến đo sáng", "Điều chỉnh lại góc quay tránh ánh sáng trực tiếp, bật WDR/BLC"
    elif "mất kết nối" in error or "offline" in error or "timeout" in error:
        return "Đứt cáp mạng, lỏng cáp, Switch cấp mạng/PoE treo hoặc mất điện", "Kiểm tra đèn tín hiệu ở Switch, đo thông mạch cáp mạng, khởi động lại Switch"
    elif "hdd" in error or "ổ cứng" in error or "error" in error:
        return "Lỗi phần cứng ổ đĩa, cáp SATA lỏng hoặc Bad Sector", "Kiểm tra cáp kết nối ổ cứng trong NVR, format hoặc thay thế HDD mới"
    else:
        return "Lỗi phần cứng hoặc đường truyền", "Kiểm tra thực tế tại hiện trường, khởi động lại thiết bị"


def main():
    base_data_dir = r"D:\Automation\src\tasks\CAMERA\data"
    snapshot_dir = r"D:\Automation\src\tasks\CAMERA\data\snapshots"
    os.makedirs(snapshot_dir, exist_ok=True)

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Camera Analysis"
    sheet.append(["Khu vực/Xưởng", "Tên Kênh", "Trạng Thái", "Thông tin HDD (Sức khỏe)", "Hệ thống", "Mô tả lỗi", "Ảnh minh họa"])
    
    log_sheet = workbook.create_sheet(title="Sổ Nhật Ký HQ")
    log_sheet.append([
        "Thời gian phát hiện", 
        "Khu vực / Xưởng", 
        "Thiết bị (NVR / Kênh)", 
        "Phân loại Lỗi", 
        "Hiện tượng (Tool ghi nhận)", 
        "Nguyên nhân (Kỹ thuật điền)", 
        "Biện pháp khắc phục", 
        "Trạng thái"
    ])

    SUSPICIOUS_CAMERAS = [] 

    print("=== BẮT ĐẦU VÒNG 1: QUÉT HỆ THỐNG DAHUA ===")
    camera_info_path = os.path.join(base_data_dir, "CameraInfo.txt")
    if os.path.exists(camera_info_path):
        with open(camera_info_path, "r") as file:
            for line in file.readlines():
                if not line.strip() or '|' not in line: continue
                factory_name, base_url, username, password = line.strip().split('|')
                print(f"\nChecking Dahua: {factory_name} ({base_url})")

                hdd_text, is_hdd_error = CameraUtility.get_hdd_status(base_url, username, password)
                sys_info = CameraUtility.get_system_info(base_url, username, password)
                ALL_HDD_STATUS.append(f"[{factory_name}] (DAHUA) - {sys_info} | HDD: {hdd_text}")
                if is_hdd_error: SYSTEM_ALERTS.append(f"{factory_name} (DAHUA): {hdd_text}")
                sheet.append([factory_name, "DEVICE_ROOT", "INFO", hdd_text, sys_info, "Thông tin đầu ghi", ""])

                channel_info = CameraUtility.get_channel_title_config(base_url, username, password)

                if not channel_info: continue
                TARGET_NVRS = ["http://101.99.46.50:8085", "http://101.99.46.50:8090"]
                current_url = base_url.strip().lower()

                for channel_id, channel_name in channel_info.items():
                    if "not in use" in channel_name.lower(): continue
                    if current_url in TARGET_NVRS:
                        search_id = channel_id
                        if current_url == "http://101.99.46.50:8090":
                            search_id = channel_id + 1 
                        oldest_date, retained_days = CameraUtility.get_oldest_record_days(base_url, username, password, search_id)
                        ALL_CAMERA_RETENTION.append({
                            "Xưởng": factory_name, 
                            "Kênh": channel_name,   
                            "Cũ nhất": oldest_date,
                            "Số ngày": retained_days
                        })
                        if retained_days < 365:
                            RETENTION_ALERTS.append({
                                "Xưởng": factory_name,
                                "Kênh": channel_name,
                                "Cũ nhất": oldest_date,
                                "Số ngày": retained_days
                            })

                    snapshot_path = os.path.join(snapshot_dir, f"{factory_name}_{channel_id}.jpg")
                    if os.path.exists(snapshot_path):
                        os.remove(snapshot_path)
                        
                    # ==================================
                    # CỐ GẮNG CHỤP VÀ ĐÁNH GIÁ DAHUA
                    # ==================================
                    if CameraUtility.get_snapshot(base_url, username, password, channel_id, snapshot_path):
                        result = classify_image(snapshot_path)
                        if not result["error"]:
                            sheet.append([factory_name, channel_name, "OK", "-", "-", "", ""])
                        else:
                            print(f"[-] LỖI AI: {factory_name} - {channel_name} ({result['description']})")
                            sheet.append([factory_name, channel_name, "NG", "-", "-", result["description"], ""])
                            NG_CAMERAS.append({
                                "path": snapshot_path, 
                                "Xưởng": factory_name, 
                                "Kênh": channel_name, 
                                "reason": result["description"]
                            })
                            
                        # Chèn ảnh cho DAHUA
                        current_row = sheet.max_row
                        try:
                            img = Image(snapshot_path)
                            img.width, img.height = 240, 135
                            sheet.add_image(img, f"G{current_row}")
                            sheet.column_dimensions["G"].width = img.width / 7
                            sheet.row_dimensions[current_row].height = img.height
                        except: pass
                    else:
                        print(f"[?] MẤT KẾT NỐI: {factory_name} - {channel_name} -> Chờ kiểm tra lại sau 5p")
                        SUSPICIOUS_CAMERAS.append({
                            "brand": "Dahua", 
                            "factory": factory_name, 
                            "url": base_url, 
                            "user": username, 
                            "pass": password, 
                            "id": channel_id, 
                            "name": channel_name, 
                            "path": snapshot_path
                        })

    print("\n=== BẮT ĐẦU VÒNG 1: QUÉT HỆ THỐNG HIKVISION ===")
    hik_info_path = os.path.join(base_data_dir, "HikvisionInfo.txt")
    if os.path.exists(hik_info_path):
        with open(hik_info_path, "r") as file:
            for line in file.readlines():
                if not line.strip() or '|' not in line: continue
                factory_name, base_url, username, password = line.strip().split('|')
                print(f"\nChecking Hikvision: {factory_name} ({base_url})")

                hdd_text, is_hdd_error = HikvisionUtility.get_hdd_status(base_url, username, password)
                sys_info = HikvisionUtility.get_system_info(base_url, username, password)
                ALL_HDD_STATUS.append(f"[{factory_name}] (HIKVISION) - {sys_info} | HDD: {hdd_text}")
                if is_hdd_error: SYSTEM_ALERTS.append(f"{factory_name} (HIK): {hdd_text}")
                sheet.append([factory_name, "DEVICE_ROOT", "INFO", hdd_text, sys_info, "Thông tin đầu ghi", ""])

                channel_info = HikvisionUtility.get_channel_title_config(base_url, username, password)
                if not channel_info: continue

                for channel_id, channel_name in channel_info.items():
                    if "not in use" in channel_name.lower(): continue
                    snapshot_path = os.path.join(snapshot_dir, f"HIK_{factory_name}_{channel_id}.jpg")
                    if os.path.exists(snapshot_path):
                        os.remove(snapshot_path)
                        
                    # ==================================
                    # CỐ GẮNG CHỤP VÀ ĐÁNH GIÁ HIKVISION
                    # ==================================
                    if HikvisionUtility.get_snapshot(base_url, username, password, channel_id, snapshot_path):
                        result = classify_image(snapshot_path)
                        if not result["error"]:
                            print(f"{factory_name} - {channel_name}: OK")
                            sheet.append([factory_name, channel_name, "OK", "-", "-", "", ""])
                        else:
                            print(f"[-] LỖI AI: {factory_name} - {channel_name} ({result['description']})")
                            sheet.append([factory_name, channel_name, "NG", "-", "-", result["description"], ""])
                            NG_CAMERAS.append({
                                "path": snapshot_path, 
                                "Xưởng": factory_name, 
                                "Kênh": channel_name, 
                                "reason": result["description"]
                            })

                        # Chèn ảnh cho HIKVISION
                        current_row = sheet.max_row
                        try:
                            img = Image(snapshot_path)
                            img.width, img.height = 240, 135
                            sheet.add_image(img, f"G{current_row}")
                            sheet.column_dimensions["G"].width = img.width / 7
                            sheet.row_dimensions[current_row].height = img.height
                        except: pass
                    else:
                        print(f"[?] NGHI NGỜ: {factory_name} - {channel_name} (Mất kết nối)")
                        SUSPICIOUS_CAMERAS.append({"brand": "Hikvision", "factory": factory_name, "url": base_url, "user": username, "pass": password, "id": channel_id, "name": channel_name, "path": snapshot_path})


    if SUSPICIOUS_CAMERAS:
        print("\n==========================================================")
        print(f"[*] CẢNH BÁO: Phát hiện {len(SUSPICIOUS_CAMERAS)} camera có dấu hiệu NG.")
        print("[*] Kích hoạt cơ chế theo dõi liên tục trong 30 phút (Check mỗi 1 phút)...")
        print("==========================================================")
        
        still_suspicious = SUSPICIOUS_CAMERAS.copy()
        max_retries = 30 
        
        for attempt in range(1, max_retries + 1):
            if not still_suspicious:
                print("\n[+] Tuyệt vời! Toàn bộ camera nghi ngờ đều đã phục hồi mạng.")
                break 
                
            print(f"\n[*] Lần thử {attempt}/{max_retries} (Đang chờ 1 phút trước khi check...)")
            time.sleep(60) 
            
            failed_this_attempt = []
            for cam in still_suspicious:
                print(f"Re-checking {cam['factory']} - {cam['name']}...")
                is_success = False
                final_reason = ""
                
                if cam["brand"] == "Dahua":
                    success_snap = CameraUtility.get_snapshot(cam["url"], cam["user"], cam["pass"], cam["id"], cam["path"])
                else:
                    success_snap = HikvisionUtility.get_snapshot(cam["url"], cam["user"], cam["pass"], cam["id"], cam["path"])

                if success_snap:
                    result = classify_image(cam["path"])
                    if not result["error"]:
                        is_success = True
                    else:
                        final_reason = result["description"]
                else:
                    final_reason = "Mất kết nối/Timeout (Chưa phục hồi)"

                if is_success:
                    print(f"-> ✅ ĐÃ PHỤC HỒI MẠNG: {cam['factory']} - {cam['name']}")
                    sheet.append([cam["factory"], cam["name"], "OK", "-", "-", f"Đã phục hồi sau {attempt} phút rớt mạng", ""])
                    current_row = sheet.max_row
                    try:
                        img = Image(cam["path"])
                        img.width, img.height = 240, 135
                        sheet.add_image(img, f"G{current_row}")
                        sheet.column_dimensions["G"].width = img.width / 7
                        sheet.row_dimensions[current_row].height = img.height
                    except: pass
                else:
                    print(f"-> ⏳ VẪN CHƯA PHỤC HỒI: {cam['factory']} - {cam['name']} ({final_reason})")
                    cam["last_reason"] = final_reason 
                    failed_this_attempt.append(cam) 
                    
            still_suspicious = failed_this_attempt
            
        if still_suspicious:
            print("\n=== ĐÃ HẾT 30 PHÚT THEO DÕI. CHỐT KẾT QUẢ CÁC CAMERA CHẾT THẬT SỰ ===")
            for cam in still_suspicious:
                reason = cam.get("last_reason", "Mất kết nối (Đã rớt mạng > 30 phút)")
                print(f"-> ☠️ CHẾT THẬT SỰ: {cam['factory']} - {cam['name']} ({reason})")
                
                sheet.append([cam["factory"], cam["name"], "NG", "-", "-", f"{reason} (Kéo dài > 30p)", ""])
                current_row = sheet.max_row
                try:
                    img = Image(cam["path"])
                    img.width, img.height = 240, 135
                    sheet.add_image(img, f"G{current_row}")
                    sheet.column_dimensions["G"].width = img.width / 7
                    sheet.row_dimensions[current_row].height = img.height
                except: pass
                
                NG_CAMERAS.append({
                    "path": cam["path"] if os.path.exists(cam["path"]) else None, 
                    "Xưởng": cam["factory"], 
                    "Kênh": cam["name"], 
                    "reason": f"{reason} (> 30 phút)"
                })

    # =========================================================================
    # GHI DỮ LIỆU VÀO SHEET 2 (SỔ NHẬT KÝ HẢI QUAN CÓ TÍNH NĂNG NHỚ TRẠNG THÁI)
    # =========================================================================
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    processed_hq_cams = set() 
    
    # --- ĐỌC BỘ NHỚ LỊCH SỬ (Tình trạng camera của ngày hôm qua) ---
    history_file = os.path.join(base_data_dir, "hq_camera_history.json")
    old_history = {}
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                old_history = json.load(f)
        except: pass
        
    new_history = {} 

    # 1. Ghi nhận LỖI LỚN TỪ HỆ THỐNG
    for alert in SYSTEM_ALERTS:
        if "8085" in alert or "8090" in alert or "Hai Quan" in alert:
            factory_extract = alert.split(']')[0].replace('[', '') if '[' in alert else "Hai Quan"
            cause, solution = get_cause_and_solution(alert)
            log_sheet.append([
                current_time_str, factory_extract, "Hệ thống NVR Hải Quan", 
                "Lỗi lớn", alert, cause, solution, "" 
            ])

    # 2. Đọc danh sách TOÀN BỘ camera từ Sheet 1 để đưa sang Sổ Nhật Ký
    for row in list(sheet.rows)[1:]: 
        factory_name = str(row[0].value)
        channel_name = str(row[1].value)
        status = str(row[2].value)
        error_desc = str(row[5].value)

        if channel_name == "DEVICE_ROOT":
            continue

        if "Hai Quan" in factory_name:
            cam_key = f"{factory_name}_{channel_name}"
            processed_hq_cams.add(cam_key) 
            
            old_status = old_history.get(cam_key, "OK")
            
            if status == "OK":
                new_history[cam_key] = "OK" 
                if old_status != "OK":
                    log_sheet.append([
                        current_time_str, factory_name, channel_name,
                        "Bình thường", "✅ Đã khắc phục xong (Camera lên hình lại)", 
                        "Thiết bị đã trực tuyến và rõ nét", "-", ""
                    ])
                else:
                    log_sheet.append([
                        current_time_str, factory_name, channel_name,
                        "Bình thường", "Hoạt động tốt", "-", "-", ""
                    ])
                    
            elif status == "NG":
                new_history[cam_key] = "NG" 
                desc = error_desc if error_desc and error_desc != "-" else "Lỗi hình ảnh"
                cause, solution = get_cause_and_solution(desc)
                log_sheet.append([
                    current_time_str, factory_name, channel_name,
                    "Lỗi nhỏ", desc, cause, solution, ""
                ])

    # 3. Bổ sung các camera Hải Quan bị mất kết nối mạng hoàn toàn 
    for cam in SUSPICIOUS_CAMERAS:
        factory_name = cam.get("factory", "Unknown")
        channel_name = cam.get("name", "Unknown")
        
        if "Hai Quan" in factory_name:
            cam_key = f"{factory_name}_{channel_name}"
            if cam_key not in processed_hq_cams:
                new_history[cam_key] = "NG" 
                cause, solution = get_cause_and_solution("Mất kết nối mạng")
                log_sheet.append([
                    current_time_str, factory_name, channel_name,
                    "Lỗi nhỏ", "Mất kết nối mạng / Không thể chụp ảnh",
                    cause, solution, ""
                ])
                processed_hq_cams.add(cam_key)

    # --- LƯU LẠI BỘ NHỚ CHO NGÀY MAI ---
    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(new_history, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Lỗi lưu lịch sử HQ: {e}")

    # =========================================================================
    # LƯU EXCEL TỔNG VÀ GỬI MAIL
    # =========================================================================
    current_date = datetime.now().strftime("%Y%m%d")
    output_path = fr"N:\Ｃ：ＮＩＶＳ総務・人事(GA&HR)\０４：ＩＴ\１７：RPA Report\1. Camera\CameraAnalysis_{current_date}.xlsx"
    workbook.save(output_path)
    
    send_alert_email()
    print(f"Results saved to {output_path}")

if __name__ == "__main__":
    main()