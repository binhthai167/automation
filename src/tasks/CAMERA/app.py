import streamlit as st
import os
import requests
from requests.auth import HTTPDigestAuth
from datetime import datetime, time as dt_time
import re
import uuid
from datetime import timedelta
import json
from PIL import Image
import io
import streamlit.components.v1 as components
import unicodedata
import glob
import time




def cleanup_old_videos(temp_dir="temp_videos", max_age_hours=2):
    """Xóa các file video MP4 đã lưu quá thời gian quy định để giải phóng ổ cứng"""
    now = time.time()
    for f in glob.glob(os.path.join(temp_dir, "*.mp4")):
        # Nếu thời gian tạo file cũ hơn (max_age_hours * 3600 giây) thì xóa
        if os.stat(f).st_mtime < now - (max_age_hours * 3600):
            try:
                os.remove(f)
            except: pass
# ==========================================
# CẤU HÌNH TRANG (PHẢI NẰM ĐẦU TIÊN)
# ==========================================
st.set_page_config(page_title="CCTV Downloader", page_icon="🎥", layout="wide", initial_sidebar_state="collapsed")

# ==========================================
# 1. HÀM TỰ ĐỘNG ĐỌC FILE CẤU HÌNH JSON
# ==========================================
def load_config():
    config_path = "camera_config.json"
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
        # SỬA Ở ĐÂY: Dùng thẳng giờ Local và nối thêm múi giờ +07:00 (Bỏ việc trừ 7 tiếng)
        st_search = start_time.strftime("%Y-%m-%dT%H:%M:%S+07:00")
        et_search = end_time.strftime("%Y-%m-%dT%H:%M:%S+07:00")
        
        try:
            chan_num = int(channel)
        except ValueError:
            return False, "Lỗi ID Kênh trong cấu hình!"
            
        channels_to_try = [f"{chan_num}01", f"{chan_num+32}01", str(chan_num)]
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
# PHẦN 1: TẠO BỘ NHỚ TẠM & HÀM ĐỌC FILE TXT
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.current_user = "" 

def load_users_from_txt(filepath="users.txt"):
    users_db = {}
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip() 
                if line and ':' in line:
                    user, pwd = line.split(':', 1)
                    users_db[user.strip()] = pwd.strip()
    return users_db

def show_camera_snapshot(brand, ip, username, password, channel_id):
    try:
        if brand == "Hikvision":
            url = f"http://{ip}/ISAPI/Streaming/channels/{channel_id}01/picture"
        elif brand == "Dahua":
            url = f"http://{ip}/cgi-bin/snapshot.cgi?channel={channel_id}"
            
        response = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=5)
        
        if response.status_code == 200:
            image = Image.open(io.BytesIO(response.content))
            st.image(image, caption=f"📸 Cập nhật trực tiếp: Kênh số {channel_id}", use_container_width=True)
        else:
            st.error(f"Không thể lấy ảnh. Mã lỗi thiết bị: {response.status_code}")
    except Exception as e:
        st.error(f"Lỗi mất kết nối mạng đến NVR ({ip}): {e}")

# Hàm xử lý giao diện đăng nhập
def show_login_page():
    st.title("HỆ THỐNG TRÍCH XUẤT CAMERA")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.info("Vui lòng đăng nhập để sử dụng hệ thống.")
        username = st.text_input("Tài khoản:")
        password = st.text_input("Mật khẩu:", type="password")
        
        if st.button("Đăng nhập", use_container_width=True):
            users_db = load_users_from_txt("users.txt")
            if not users_db:
                st.error("Lỗi: Không tìm thấy dữ liệu tài khoản trong hệ thống!")
                return
            
            if username in users_db and users_db[username] == password:
                st.session_state.logged_in = True
                st.session_state.current_user = username
                st.success(f"Đăng nhập thành công! Chào mừng {username}...")
                st.rerun() 
            else:
                st.error("Sai tài khoản hoặc mật khẩu. Vui lòng thử lại!")

if not st.session_state.logged_in:
    show_login_page()
    st.stop()

col_chao, col_nut = st.columns([8, 2]) 
with col_chao:
    st.markdown(f"### 👤 Xin chào: **{st.session_state.current_user.upper()}**")
with col_nut:
    if st.button("🚪 Đăng xuất", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.current_user = ""
        st.rerun()

st.markdown("---")

def tao_ten_path(chuoi):
    """Hàm biến tên Xưởng thành tên path viết liền không dấu (Khớp 100% với file yml)"""
    chuoi = unicodedata.normalize('NFKD', chuoi).encode('ASCII', 'ignore').decode('utf-8')
    chuoi = chuoi.lower()
    chuoi = re.sub(r'[^a-z0-9]', '_', chuoi)
    return re.sub(r'_+', '_', chuoi).strip('_')

st.sidebar.markdown("---")
st.sidebar.markdown("### 🌐 Mạng truy cập")
mang_truy_cap = st.sidebar.radio(
    "Bạn đang dùng mạng nào?",
    options=[
        "🏢 Mạng Nội bộ", 
        "🌍 Mạng Ngoài (Internet)"
    ]
)

# Tự động đổi IP để gọi luồng Video (Cổng 1984 của go2rtc)
if "Nội bộ" in mang_truy_cap:
    SERVER_IP = "160.20.120.5"     # Trực tiếp đâm vào máy ảo
else:
    SERVER_IP = "192.168.50.237"

# ==========================================
# 3. GIAO DIỆN WEB THÔNG MINH
# ==========================================

st.title("🎥 TRÍCH XUẤT VIDEO CAMERA")
st.markdown("Chọn xưởng và camera để tải file video MP4.")
tab1, tab2 = st.tabs(["📥 TRÍCH XUẤT VIDEO", "📺 XEM TRỰC TIẾP (MULTI-VIEW)"])

with tab1:
    temp_dir = "temp_videos"
    os.makedirs(temp_dir, exist_ok=True)
    cleanup_old_videos(temp_dir)

    # Khung chọn Hãng, Xưởng và Camera (Chia làm 3 cột)
    col1, col2, col3 = st.columns(3)

    with col1:
        list_brands = list(set([info["brand"] for info in CAMERA_CONFIG.values()]))
        selected_brand = st.selectbox("🏷️ Chọn Hãng Camera", sorted(list_brands, reverse=False))

    with col2:
        list_xuong = [xuong for xuong, info in CAMERA_CONFIG.items() if info["brand"] == selected_brand]
        if list_xuong:
            selected_xuong = st.selectbox("🏭 Chọn Khu vực / Xưởng", list_xuong)
        else:
            selected_xuong = st.selectbox("🏭 Chọn Khu vực / Xưởng", ["Chưa có dữ liệu"])

    with col3:
        if selected_xuong and selected_xuong != "Chưa có dữ liệu":
            list_camera = list(CAMERA_CONFIG[selected_xuong]["channels"].keys())
            selected_camera = st.selectbox("📹 Chọn Camera", list_camera)
        else:
            selected_camera = st.selectbox("📹 Chọn Camera", ["Chưa có dữ liệu"])
    if selected_camera and selected_camera != "Chưa có dữ liệu" and selected_xuong != "Chưa có dữ liệu":
        sys_info = CAMERA_CONFIG[selected_xuong]
        cam_channel_id = sys_info["channels"][selected_camera]
        
        path_name = f"{tao_ten_path(selected_xuong)}_cam{cam_channel_id}"
        # Tạo đường link nhúng chuẩn MSE của go2rtc (Sử dụng cổng 1984)
        player_url = f"http://{SERVER_IP}:1984/stream.html?src={path_name}&mode=mse"

        # Nhúng vào Streamlit
        st.components.v1.iframe(player_url, width=800, height=450)
        

    st.markdown("---")
    st.subheader("📅 Chọn thời gian xem lại")
    col_date1, col_date2 = st.columns(2)
    with col_date1:
        date_start = st.date_input("Ngày bắt đầu")
        time_start = st.time_input("Giờ bắt đầu", value=dt_time(8, 0))
    with col_date2:
        date_end = st.date_input("Ngày kết thúc")
        time_end = st.time_input("Giờ kết thúc", value=dt_time(8, 15))

    start_time = datetime.combine(date_start, time_start)
    end_time = datetime.combine(date_end, time_end)

    if st.button("🚀 XỬ LÝ & TRÍCH XUẤT", use_container_width=True):
        if selected_xuong == "Chưa có dữ liệu" or selected_camera == "Chưa có dữ liệu":
            st.error("⚠️ Vui lòng cấu hình dữ liệu Xưởng và Camera trước khi tải!")
        elif start_time >= end_time:
            st.error("⚠️ Thời gian bắt đầu phải nhỏ hơn thời gian kết thúc!")
        else:
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

with tab2:
    # Gom danh sách camera để chọn
    all_cams = []
    for x, info in CAMERA_CONFIG.items():
        for c in info["channels"].keys():
            all_cams.append(f"{x} | {c}")
            
    selected_list = st.multiselect(
        "Chọn tối đa 5 Camera để xem cùng lúc:",
        options=all_cams,
        max_selections=5,
        default=all_cams[:5] if len(all_cams) >= 5 else all_cams # Load thử 5 cam đầu tiên
    )
    
    if selected_list:
        # 1. Xác định số lượng camera để chọn lưới Grid phù hợp
        num_cams = len(selected_list)
        if num_cams == 1: grid_class = "grid-1"
        elif num_cams == 2: grid_class = "grid-2"
        elif num_cams == 3: grid_class = "grid-3"
        elif num_cams == 4: grid_class = "grid-4"
        else: grid_class = "grid-5" # Cho 5 camera
        
        # 2. Xây dựng khối HTML và CSS Grid Động (ÉP SÁT LỀ TRÁI ĐỂ TRÁNH LỖI MARKDOWN)
        html_content = f"""
<style>
/* Khung chứa tổng: Chiếm đúng 75% chiều cao màn hình */
.cam-dashboard {{
    display: grid;
    gap: 10px;
    width: 100%;
    height: 75vh; 
    margin-top: 10px;
}}

/* Thuật toán chia lưới thông minh */
.grid-1 {{ grid-template-columns: 1fr; grid-template-rows: 1fr; }}
.grid-2 {{ grid-template-columns: repeat(2, 1fr); grid-template-rows: 1fr; }}
.grid-3 {{ grid-template-columns: repeat(3, 1fr); grid-template-rows: 1fr; }}
.grid-4 {{ grid-template-columns: repeat(2, 1fr); grid-template-rows: repeat(2, 1fr); }}
.grid-5 {{ grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(2, 1fr); }}

/* Trang trí từng ô Camera */
.cam-item {{
    border: 2px solid #333;
    border-radius: 8px;
    position: relative;
    overflow: hidden;
    background-color: #000;
    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
}}

/* Tên Camera nổi lên trên góc trái video */
.cam-title {{
    position: absolute;
    top: 0; left: 0;
    background: rgba(0, 0, 0, 0.7);
    color: #00FF00;
    padding: 4px 12px;
    font-family: sans-serif;
    font-size: 14px;
    font-weight: bold;
    z-index: 10;
    border-bottom-right-radius: 8px;
}}

/* Bắt buộc Iframe video phải giãn vừa khít 100% ô Grid */
.cam-iframe {{
    width: 100%;
    height: 100%;
    border: none;
}}
</style>

<div class="cam-dashboard {grid_class}">
"""
        
        # 3. Đổ dữ liệu từng Camera vào các ô Grid (CŨNG ÉP SÁT LỀ TRÁI)
        for item in selected_list:
            xuong_name, cam_name = item.split(" | ")
            chan_id = CAMERA_CONFIG[xuong_name]["channels"][cam_name]
            path_name = f"{tao_ten_path(xuong_name)}_cam{chan_id}"
            
            # ĐÃ SỬA LẠI ĐƯỜNG LINK Ở ĐÂY SANG go2rtc (Cổng 1984)
            url = f"http://{SERVER_IP}:1984/stream.html?src={path_name}&mode=mse"
            
            html_content += f"""
<div class="cam-item">
    <div class="cam-title">📍 {xuong_name} - {cam_name}</div>
    <iframe class="cam-iframe" src="{url}" allowfullscreen></iframe>
</div>
"""
            
        html_content += "</div>"
        
        # 4. Hiển thị toàn bộ khối giao diện lên Streamlit
        st.markdown(html_content, unsafe_allow_html=True)
    else:
        st.warning("Vui lòng chọn ít nhất một camera để xem.")
