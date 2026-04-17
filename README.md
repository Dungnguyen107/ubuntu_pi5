# **DỰ ÁN SỬ DỤNG RASPBERRY PI 5 VỚI HỆ ĐIỀU HÀNH UBUNTU **

Đây là dự án được thực hiện trên Raspberry Pi 5, chạy hệ điều hành Ubuntu, sử dụng picamera module 3, đang thực hiện test FastAPI, Websockets và camera streaming

## I. Overview (Tổng quan)
Dự án này hiện tại được xây dựng để chạy trên Raspberry Pi 5 và phục vụ cho việc:

- tạo web server bằng FastAPI
- hiển thị giao diện web trên trình duyệt
- stream hình ảnh từ camera lên web
- đọc dữ liệu UART từ thiết bị ngoài
- gửi dữ liệu UART lên giao diện web bằng WebSocket

Mục tiêu của project là tạo nền tảng dashboard thời gian thực để theo dõi dữ liệu và hiển thị camera trên Pi 5.

---

## II. Project Structure (Cấu trúc dự án)

```text
ubuntu_pi5/
├── app/                 # Python app files, HTML templates, server code
├── bin/                 # Compiled binaries such as uart_reader
├── requirements.txt     # Python dependencies
├── .gitignore
└── README.md
```

## III. Môi trường sử dụng

- Raspberry Pi 5
- Ubuntu
- Python 3
- FastAPI
- Uvicorn
- Picamera2
- UART qua cổng như `/dev/ttyUSB0`
---
## IV. **HƯỚNG DẪN CLONE VÀ CHẠY DỰ ÁN TRÊN UBUNTU'
### 1. BƯỚC 1: CÀI UBUNTU CHO PI5
Xem link youtube được đính kèm dưới đây và thực hiện theo, đến bước có thể ssh vào pi5 hoặc truy cập qua ssh của VScode, hoặc có màn hình rời cho PI5
`https://www.youtube.com/watch?v=5CBYGz_mO9U`

### 2. BƯỚC 2: THỬ NGHIỆM CAMERA (Nếu không dùng cam stream thì skip)
- THỰC HIỆN KĨ, BÁM SÁT TỪNG BƯỚC TRONG FILE ĐƯỢC ĐÍNH KÈM RIÊNG. Tên file: `use_cam_on_ubuntu_on_pi5.md`

### 3. BƯỚC 3: CLONE THƯ MỤC DỰ ÁN VÀ TẠO MÔI TRƯỜNG ẢO
- Clone thư mục về pi5 của bạn và cd vào thư mục đó.
```bash
git clone https://github.com/Dungnguyen107/ubuntu_pi5.git
```

- **TẠO VENV VÀ KÍCH HOẠT VENV** (rất dễ lỗi, xem chi tiết trong phần hướng dẫn và file test cam).
```bash
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install --upgrade pip
pip install picamera2
echo "/usr/local/lib/python3/dist-packages" > ~/Documents/ubuntu_pi5/.venv/lib/python3.12/site-packages/libcamera.pth 
```

- **CÀI CÁC THƯ VIỆN QUAN TRỌNG NHƯ LIBCAMERA, PICAMERA 2 THEO FILE TEST CAM**
```bash
cat > ~/Documents/ubuntu_pi5/.venv/lib/python3.12/site-packages/picamera2/previews/__init__.py << 'EOF'
try:
    from .drm_preview import DrmPreview
except Exception:
    class DrmPreview:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("DrmPreview không khả dụng (thiếu pykms)")

from .null_preview import NullPreview
from .qt_previews import QtGlPreview, QtPreview
EOF
```
- Cài các thư viện cần thiết theo requirements.txt
```bash
pip install -r requirements.txt
```
- Build file C nếu thiếu
```bash
gcc uart_reader.c -o bin/uart_reader
```
 ### 4. BƯỚC 4: CHẠY THỬ NGHIỆM TỪNG MODULE Ở MỖI PORT
 - Chạy stream camera:
 ```python3 -m app.server_cam```

 - Chạy ws xem log uart:
 ```python3 -m app.server_cam```

 Xem kết quả:
 - Camera: ```http://[ip_cua_pi5]:8002```
 - UART: ```http://[ip_cua_pi5]:8001```
 ví dụ: *http://192.168.0.110:8001*
