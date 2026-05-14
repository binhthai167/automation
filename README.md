# Hệ Thống Tự Động Hóa NIVS (NIDEV Vietnam Solution)

## Tổng Quan

Dự án này là một hệ thống tự động hóa gồm ba thành phần chính:
1. **Kiểm tra sức khỏe máy chủ iLO** - Tự động kiểm tra tình trạng sức khỏe của các máy chủ HP iLO thông qua giao thức Redfish
2. **Phân tích camera thông minh** - Phân tích hình ảnh từ camera để phát hiện lỗi thiết bị sử dụng AI
3. **Dashboard EDMS** - Dashboard trực quan hóa dữ liệu quy trình làm việc từ hệ thống quản lý văn bản điện tử

## Cấu Trúc Thư Mục

```
Automation/
├── iLO.py                 # Script kiểm tra sức khỏe máy chủ iLO
├── Camera.py             # Script phân tích hình ảnh camera
├── EDMSReport.py         # Ứng dụng dashboard Streamlit cho EDMS
├── iLODaily.bat          # Batch script chạy kiểm tra iLO hàng ngày
├── CamDaily.bat          # Batch script chạy phân tích camera hàng ngày
├── EDMS.bat              # Batch script chạy dashboard EDMS
├── requirements.txt      # Danh sách thư viện phụ thuộc
├── data/                 # Thư mục chứa dữ liệu đầu vào
│   ├── ILO Server.xlsx   # Danh sách máy chủ iLO cần kiểm tra
│   ├── CameraInfo.txt    # Thông tin đăng nhập camera
│   └── snapshot.jpg      # Ảnh chụp tạm thời từ camera
└── logs/                 # Thư mục lưu log hệ thống
```

## Thành Phần 1: Kiểm Tra Sức Khỏe Máy Chủ iLO

### Mô Tả
Script `iLO.py` sử dụng giao thức Redfish để kết nối đến các máy chủ HP iLO và thu thập thông tin sức khỏe hệ thống, bao gồm:
- Trạng thái Agentless Management Service
- Sức khỏe BIOS/Hardware
- Trạng thái quạt và dự phòng quạt
- Sức khỏe RAM, CPU, bộ nguồn
- Trạng thái lưu trữ và nhiệt độ
- Trạng thái mạng

### Cách Hoạt Động
1. Đọc danh sách máy chủ từ file `data/ILO Server.xlsx`
2. Kết nối đến từng máy chủ iLO sử dụng thông tin đăng nhập
3. Thu thập dữ liệu sức khỏe thông qua API Redfish
4. Xuất kết quả ra file Excel với tên theo ngày (yyyymmdd)

### Cấu Trúc File Dữ Liệu iLO
File `data/ILO Server.xlsx` cần chứa các cột:
- Server Name: Tên máy chủ
- Notes: Gồm IP và thông tin đăng nhập theo định dạng:
  ```
  [IP Address]
  -u [username] -p [password]
  ```

## Thành Phần 2: Phân Tích Camera Thông Minh

### Mô Tả
Script `Camera.py` thực hiện:
- Kết nối đến các camera qua giao thức HTTP Digest
- Chụp ảnh từ các kênh camera
- Phân tích hình ảnh để phát hiện lỗi thiết bị sử dụng AI
- Lưu kết quả vào file Excel báo cáo

### Cách Phát Hiện Lỗi
Script sử dụng hai phương pháp:
1. **Phân tích truyền thống**: Phát hiện các lỗi như màn hình đen/trắng, nhiễu, sọc ngang/dọc
2. **Phân tích AI**: Sử dụng mô hình ngôn ngữ hình ảnh để phân tích chất lượng hình ảnh

Các lỗi thiết bị được phát hiện bao gồm:
- Màn hình đen hoàn toàn (không có chi tiết)
- Màn hình trắng hoàn toàn (không có chi tiết)
- Hình ảnh có sọc ngang/dọc bất thường
- Nhiễu quá mức (pixel lỗi)
- Lens bị che khuất hoàn toàn
- Hình ảnh bị lật ngược/xoay sai
- Khung hình bị cắt xén/biến dạng
- Hiển thị thông báo lỗi hệ thống
- Đóng băng hình ảnh (freeze frame)

### Cấu Trúc File Dữ Liệu Camera
File `data/CameraInfo.txt` có định dạng:
```
[Tên nhà máy]|[URL camera]|[Tên người dùng]|[Mật khẩu]
```

## Thành Phần 3: Dashboard EDMS

### Mô Tả
Ứng dụng `EDMSReport.py` là một dashboard Streamlit cung cấp:
- Giao diện trực quan hóa dữ liệu quy trình làm việc từ hệ thống EDMS
- Biểu đồ hiệu suất theo phòng ban và loại biểu mẫu
- Bộ lọc thời gian và lựa chọn dữ liệu
- Khả năng xuất dữ liệu dưới dạng CSV

### Số Hiệu Suất Chính (KPIs)
- Tổng số biểu mẫu
- Số biểu mẫu đã hoàn thành
- Số biểu mẫu đang chờ
- Tỷ lệ hoàn thành
- Thời gian xử lý trung bình
- Số biểu mẫu quá hạn
- Số biểu mẫu cơ sở được tạo

## Yêu Cầu Hệ Thống

### Phụ Thuộc (Dependencies)
Tất cả các thư viện phụ thuộc được liệt kê trong `requirements.txt`:
- streamlit: Framework giao diện người dùng
- pandas: Xử lý dữ liệu
- sqlalchemy: Kết nối cơ sở dữ liệu
- mysql-connector-python: Kết nối MySQL
- opencv-python: Xử lý hình ảnh
- openai: Giao tiếp với API AI
- python-ilorest-library: Thư viện Redfish cho iLO
- plotly: Biểu đồ trực quan hóa
- requests: Giao tiếp HTTP

### Cài Đặt
1. Cài đặt Python 3.8 trở lên
2. Tạo môi trường ảo:
   ```bash
   python -m venv .venv
   ```
3. Kích hoạt môi trường ảo:
   ```bash
   # Trên Windows
   .venv\Scripts\activate
   ```
4. Cài đặt các thư viện phụ thuộc:
   ```bash
   pip install -r requirements.txt
   ```

## Cách Sử Dụng

### Chạy Kiểm Tra iLO
```bash
python iLO.py
```
Hoặc chạy bằng batch script:
```bash
iLODaily.bat
```

### Chạy Phân Tích Camera
```bash
python Camera.py
```
Hoặc chạy bằng batch script:
```bash
CamDaily.bat
```

### Chạy Dashboard EDMS
```bash
streamlit run EDMSReport.py
```
Hoặc chạy bằng batch script:
```bash
EDMS.bat
```

### Thiết Lập Lịch Trình Hàng Ngày (Daily Schedule)

Để tự động hóa việc chạy các tác vụ kiểm tra iLO và phân tích camera hàng ngày, bạn có thể sử dụng Windows Task Scheduler để thiết lập lịch trình tự động. Dưới đây là hướng dẫn chi tiết:

#### Thiết Lập Tác Vụ Cho iLO Daily

1. Mở **Task Scheduler** bằng cách gõ "Task Scheduler" trong Start Menu và chọn ứng dụng
2. Ở khung bên phải, chọn **"Create Basic Task..."**
3. Đặt tên tác vụ (ví dụ: "iLO Daily Health Check") và mô tả nếu muốn, sau đó nhấn Next
4. Chọn kích hoạt **"Daily"** và nhấn Next
5. Thiết lập thời gian bắt đầu (ví dụ: 8:00 AM), chọn tần suất hàng ngày và nhấn Next
6. Chọn **"Start a program"** và nhấn Next
7. Trong tab **"Program/script"**, nhập đường dẫn đến file batch: `iLODaily.bat`
8. Trong tab **"Start in"**, nhập đường dẫn thư mục chứa file batch: `.` (hoặc thư mục chứa dự án)
9. Nhấn Next và Finish để hoàn tất

#### Thiết Lập Tác Vụ Cho Camera Daily

1. Mở **Task Scheduler** bằng cách gõ "Task Scheduler" trong Start Menu và chọn ứng dụng
2. Ở khung bên phải, chọn **"Create Basic Task..."**
3. Đặt tên tác vụ (ví dụ: "Camera Daily Analysis") và mô tả nếu muốn, sau đó nhấn Next
4. Chọn kích hoạt **"Daily"** và nhấn Next
5. Thiết lập thời gian bắt đầu (đề xuất sau thời gian chạy iLO để tránh xung đột tài nguyên), nhấn Next
6. Chọn **"Start a program"** và nhấn Next
7. Trong tab **"Program/script"**, nhập đường dẫn đến file batch: `CamDaily.bat`
8. Trong tab **"Start in"**, nhập đường dẫn thư mục chứa file batch: `.` (hoặc thư mục chứa dự án)
9. Nhấn Next và Finish để hoàn tất

#### Cấu Hình Nâng Cao (Tùy Chọn)

Để đảm bảo tác vụ chạy đúng ngay cả khi người dùng không đăng nhập, bạn nên cấu hình thêm trong tab "General":
- Chọn "Run whether user is logged on or not" để tác vụ chạy ngay cả khi không có người đăng nhập
- Chọn "Run with highest privileges" nếu script cần quyền admin

Ngoài ra, trong tab "Settings", bạn có thể chọn "Allow task to be run on demand" để có thể chạy tác vụ bất cứ lúc nào để kiểm tra.

## Đường Dẫn Xuất Dữ Liệu

- Kết quả kiểm tra iLO được lưu tại: `N:\Ｃ：ＮＩＶＳ総務・人事(GA&HR)\０４：ＩＴ\１７：RPA Report\2. Server\[yyyymmdd].xlsx`
- Kết quả phân tích camera được lưu tại: `N:\Ｃ：ＮＩＶＳ総務・人事(GA&HR)\０４：ＩＴ\１７：RPA Report\1. Camera\CameraAnalysis_[yyyymmdd].xlsx`
#   a u t o m a t i o n  
 