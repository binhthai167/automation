import streamlit as st
import os
import requests
from requests.auth import HTTPDigestAuth
from datetime import datetime, time
import re
import uuid
from datetime import timedelta
import json

# ==========================================
# 1. HÀM TỰ ĐỘNG ĐỌC FILE CẤU HÌNH JSON
# ==========================================
def load_config():
    config_path = "config.json"
    if not os.path.exists(config_path):
        st.error(f"⚠️ LỖI: Không tìm thấy file {config_path}! Vui lòng tạo file này.")
        return {}
        
    try:
        with open(config_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        st.error(f"⚠️ LỖI: File config.json sai định dạng! Chi tiết: {str(e)}")
        return {}

# Tải cấu hình vào biến toàn cục ngay khi mở Web
CAMERA_CONFIG = load_config()
# ==========================================
class CCTVDownloader:
    @staticmethod
    def download_dahua(ip, username, password, channel, start_time, end_time, output_path):
        st_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        et_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        url = f"http://{ip}/cgi-bin/loadfile.cgi?action=startLoad&channel={channel}&startTime={st_str}&endTime={et_str}"
        
        try:
            response = requests.get(url, auth=HTTPDigestAuth(username, password), stream=True, timeout=15)
            if response.status_code == 200:
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024*1024):
                        if chunk: f.write(chunk)
                return True, "Tải thành công!"
            else:
                return False, f"Dahua từ chối (Lỗi {response.status_code})"
        except Exception as e:
            return False, f"Lỗi mạng: {str(e)}"

    @staticmethod
    def download_hikvision(ip, username, password, channel, start_time, end_time, output_path):
        st_utc = start_time - timedelta(hours=7)
        et_utc = end_time - timedelta(hours=7)
        
        st_search = st_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        et_search = et_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        try:
            chan_num = int(channel)
        except ValueError:
            return False, "Lỗi ID Kênh trong cấu hình!"
            
        channels_to_try = [f"{chan_num}01", f"{chan_num+32}01", str(chan_num)]
        last_error = ""
        headers = {'Content-Type': 'application/xml'}
        
        for chan_id in channels_to_try:
            search_url = f"http://{ip}/ISAPI/ContentMgmt/search"
            search_id = str(uuid.uuid4()).upper() 
            search_xml = f'<CMSearchDescription><searchID>{search_id}</searchID><trackList><trackID>{chan_id}</trackID></trackList><timeSpanList><timeSpan><startTime>{st_search}</startTime><endTime>{et_search}</endTime></timeSpan></timeSpanList><maxResults>40</maxResults><searchResultPosition>0</searchResultPosition></CMSearchDescription>'

            try:
                res_search = requests.post(search_url, auth=HTTPDigestAuth(username, password), data=search_xml.encode('utf-8'), headers=headers, timeout=10)
                if res_search.status_code == 401: return False, "Sai mật khẩu!"
                elif res_search.status_code != 200: continue
                    
                uri_match = re.search(r'<playbackURI[^>]*>(.*?)</playbackURI>', res_search.text)
                if not uri_match: continue
                    
                playback_uri_raw = uri_match.group(1)
                
                download_url = f"http://{ip}/ISAPI/ContentMgmt/download"
                download_xml = f'<downloadRequest><playbackURI>{playback_uri_raw}</playbackURI></downloadRequest>'
                res_dl = requests.post(download_url, auth=HTTPDigestAuth(username, password), data=download_xml.encode('utf-8'), headers=headers, stream=True, timeout=20)
                
                if res_dl.status_code == 200:
                    with open(output_path, 'wb') as f:
                        for chunk in res_dl.iter_content(chunk_size=1024*1024):
                            if chunk: f.write(chunk)
                    return True, "Trích xuất thành công!"
            except Exception as e:
                return False, f"Lỗi mạng: {str(e)}"
                
        return False, "Không tìm thấy video ở thời điểm này."

# ==========================================
# 3. GIAO DIỆN WEB THÔNG MINH
# ==========================================
st.set_page_config(page_title="CCTV Downloader", page_icon="🎥", layout="centered")

st.title("🎥 TRÍCH XUẤT VIDEO CAMERA")
st.markdown("Chọn xưởng và camera để tải file video MP4.")

temp_dir = "temp_videos"
os.makedirs(temp_dir, exist_ok=True)

# Khung chọn Hãng, Xưởng và Camera (Chia làm 3 cột)
col1, col2, col3 = st.columns(3)

with col1:
    # Tự động quét từ điển để lấy ra danh sách các hãng đang có (không bị trùng lặp)
    list_brands = list(set([info["brand"] for info in CAMERA_CONFIG.values()]))
    selected_brand = st.selectbox("🏷️ Chọn Hãng Camera", sorted(list_brands, reverse=True))

with col2:
    # Lọc ra danh sách các xưởng thuộc Hãng đã chọn ở cột 1
    list_xuong = [xuong for xuong, info in CAMERA_CONFIG.items() if info["brand"] == selected_brand]
    
    if list_xuong:
        selected_xuong = st.selectbox("🏭 Chọn Khu vực / Xưởng", list_xuong)
    else:
        selected_xuong = st.selectbox("🏭 Chọn Khu vực / Xưởng", ["Chưa có dữ liệu"])

with col3:
    # Dựa vào xưởng đã chọn ở cột 2, hiển thị danh sách Camera
    if selected_xuong and selected_xuong != "Chưa có dữ liệu":
        list_camera = list(CAMERA_CONFIG[selected_xuong]["channels"].keys())
        selected_camera = st.selectbox("📹 Chọn Camera", list_camera)
    else:
        selected_camera = st.selectbox("📹 Chọn Camera", ["Chưa có dữ liệu"])

st.markdown("---")
st.subheader("📅 Chọn thời gian xem lại")
col_date1, col_date2 = st.columns(2)
with col_date1:
    date_start = st.date_input("Ngày bắt đầu")
    time_start = st.time_input("Giờ bắt đầu", value=time(8, 0))
with col_date2:
    date_end = st.date_input("Ngày kết thúc")
    time_end = st.time_input("Giờ kết thúc", value=time(8, 15))

start_time = datetime.combine(date_start, time_start)
end_time = datetime.combine(date_end, time_end)

if st.button("🚀 XỬ LÝ & TRÍCH XUẤT", use_container_width=True):
    if selected_xuong == "Chưa có dữ liệu" or selected_camera == "Chưa có dữ liệu":
        st.error("⚠️ Vui lòng cấu hình dữ liệu Xưởng và Camera trước khi tải!")
    elif start_time >= end_time:
        st.error("⚠️ Thời gian bắt đầu phải nhỏ hơn thời gian kết thúc!")
    else:
        # Lấy thông tin để chạy
        sys_info = CAMERA_CONFIG[selected_xuong]
        ip = sys_info["ip"]
        user = sys_info["username"]
        pwd = sys_info["password"]
        brand = sys_info["brand"]
        channel_id = sys_info["channels"][selected_camera] 
        
        safe_st = start_time.strftime("%Y%m%d_%H%M")
        safe_et = end_time.strftime("%H%M")
        output_filename = f"{selected_xuong}_{selected_camera}_{safe_st}.mp4"
        output_path = os.path.join(temp_dir, output_filename)
        
        with st.spinner(f'Đang kết nối vào hệ thống {selected_xuong} để tải video. Vui lòng chờ...'):
            if brand == "Dahua":
                success, msg = CCTVDownloader.download_dahua(ip, user, pwd, channel_id, start_time, end_time, output_path)
            else:
                success, msg = CCTVDownloader.download_hikvision(ip, user, pwd, channel_id, start_time, end_time, output_path)
        
        if success:
            st.success("✅ " + msg)
            with open(output_path, "rb") as file:
                btn = st.download_button(
                    label="⬇️ BẤM VÀO ĐÂY ĐỂ LƯU VIDEO VỀ MÁY",
                    data=file,
                    file_name=output_filename,
                    mime="video/mp4",
                    type="primary",
                    use_container_width=True
                )
        else:
            st.error("❌ " + msg)