# **HƯỚNG DẪN THIẾT LẬP VÀ SỬ DỤNG PICAMERA CHO RASPBERRY PI 5 CHẠY HỆ ĐIỀU HÀNH UBUNTU**
- *File sẽ tập trung hướng dẫn sử dụng trên model picam module 3, chip imx708*
- *Các bước test để quay/chụp được đề cập là tùy chọn (optional), tức là kỹ thì làm, không thì skip cũng được*

___
# Bước 1 - Kết nối phần cứng
Cắm Picamera vô Pi5, nhớ xác định đúng xem cắm đúng chiều chưa và cắm vô cổng **cam0 hay cam 1** của Pi, vì tí nữa sửa file config sẽ cần đưa đúng tên chân để detect camera.
# Bước 2 - Cài Dependencies

```bash
sudo apt update && sudo apt upgrade -y

# Build tools
sudo apt install -y git build-essential pkg-config meson ninja-build cmake \
  python3-venv python3-dev python3-pip pybind11-dev
# Nếu ở bước 9 cài picamera2 lỗi prtcl của picamera2 thì xài thêm dòng này
sudo apt install -y build-essential libcap-dev 
# libcamera dependencies
sudo apt install -y libboost-dev libgnutls28-dev libssl-dev openssl libtiff-dev \
  libglib2.0-dev libgstreamer-plugins-base1.0-dev \
  python3-ply python3-yaml

# rpicam-apps dependencies
sudo apt install -y libboost-program-options-dev libexif-dev libavcodec-dev \
  libdrm-dev libjpeg-dev libpng-dev

# Tools debug & preview
sudo apt install -y i2c-tools v4l-utils mpv ffmpeg
```

# Bước 3 - Xóa libcamera cũ (nếu có, k có cũng xóa)
```bash
sudo apt remove --purge rpicam-apps
sudo apt remove --purge libcamera-dev libcamera0
```

# Bước 4 - Cấu hình /boot/firmware/config.txt
Vào file config.txt
```bash
sudo nano /boot/firmware/config.txt
```
Tìm dòng ```camera_auto_detect=1``` và sửa lại như sau (giữ nguyên các dòng khác):
```ini
# Thay dòng cũ:
# camera_auto_detect=1

# Thành:
camera_auto_detect=0
dtoverlay=imx708,cam0    # Nếu cắm cổng cam0
# dtoverlay=imx708,cam1  # Hoặc dùng cam1 nếu cắm cổng kia
display_auto_detect=1
```
**NHỚ REBOOT**
```bash
sudo rebot
 ```

# Bước 5 - Build  RPi libcamera fork từ source
chờ cỡ 4 5p gì đó
``` bash
cd ~
git clone https://github.com/raspberrypi/libcamera.git
cd libcamera

meson setup build --buildtype=release \
  -Dpipelines=rpi/vc4,rpi/pisp \
  -Dipas=rpi/vc4,rpi/pisp \
  -Dv4l2=enabled -Dgstreamer=enabled \
  -Dtest=false -Dlc-compliance=disabled -Dcam=disabled -Dqcam=disabled \
  -Ddocumentation=disabled -Dpycamera=enabled

ninja -C build
sudo ninja -C build install
sudo ldconfig

cd ~
```

# Bước 6 - Build rpicam-apps
```bash
cd ~
git clone https://github.com/raspberrypi/rpicam-apps.git
cd rpicam-apps

meson setup build --buildtype=release
ninja -C build
sudo ninja -C build install
sudo ldconfig

cd ~
```

# Bước 7 - Phân quyền user hoặc reboot cho dễ
```bash
sudo usermod -aG video $USER
# Đăng xuất rồi đăng nhập lại, hoặc reboot
```
``` bash
sudo reboot
```

# Bước 8 - Test Camera 
**Kiểm tra xem camera nhận chưa**
```bash
rpicam-hello --list-cameras
```

Kết quả mong đợi:
```
Available cameras
-----------------
0 : imx708_wide [4608x2592] (...)
```

**Chụp ảnh tĩnh và xem ảnh**
```rpicam-still -o test.jpg```
```ls -lh test.jpg```

**Quay video khoảng 10s xong copy qua windows coi thử**
- quay
```rpicam-vid -t 10000 --codec mjpeg -o ~/video.mjpeg```
- convert qua mp4
```ffmpeg -i ~/video.mjpeg -c:v libx264 -preset fast -crf 23 -pix_fmt yuv420p ~/video_h264.mp4```
- copy qua máy tính
```aitek@192.168.0.112:~/video_h264.mp4 D:\```

**Test camera với full độ phân giải**
```rpicam-still --width 4608 --height 2592 -o fullres.jpg```

**Debug với v412**
```bash
v4l2-ctl --list-devices
sudo dmesg | grep -i imx70
```

**Kiểm tra I2C**
```bash
sudo i2cdetect -y 10   # cho cam0 → mong đợi thấy địa chỉ 0x1a
sudo i2cdetect -y 11   # cho cam1
```

# Bước 9 - Test bằng python (picamera2)
**BƯỚC NÀY LỖI KHÁ NHIỀU NÊN FOLLOW KĨ**
Tạo thư mục project để test
```bash
mkdir -p ~/camera_test/output
cd ~/camera_test
```
Tạo venv nhưng phải cho phép build libcamera từ source
```bash
python3 -m venv --system-site-packages ~/camera_test/.venv
source ~/camera_test/.venv/bin/activate
pip install --upgrade pip
pip install picamera2
```
Thêm path libcamera
```bash
echo "/usr/local/lib/python3/dist-packages" > ~/camera_test/.venv/lib/python3.12/site-packages/libcamera.pth 
```
Patch bỏ qua DrmPreview
``` bash
cat > ~/camera_test/.venv/lib/python3.12/site-packages/picamera2/previews/__init__.py << 'EOF'
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
Test các chức năng như chụp hình/quay video
```bash
cat > ~/camera_test/capture.py << 'EOF'
import time
from picamera2 import Picamera2

cam = Picamera2()
config = cam.create_still_configuration(
    main={"size": (4608, 2592)}
)
cam.configure(config)
cam.start()

print("⏳ Đang chờ camera ổn định...")
time.sleep(2)

cam.capture_file("output/photo.jpg")
cam.stop()
print("✅ Chụp xong! Xem file output/photo.jpg")
EOF
```

```bash
cat > ~/camera_test/record.py << 'EOF'
import subprocess

print("🎥 Bắt đầu quay 10 giây...")
subprocess.run([
    "rpicam-vid",
    "-t", "10000",
    "--codec", "mjpeg",
    "--width", "1920",
    "--height", "1080",
    "-o", "output/video.mjpeg"
])
print("✅ Quay xong! Đang convert sang mp4...")
subprocess.run([
    "ffmpeg", "-y",
    "-i", "output/video.mjpeg",
    "-c:v", "libx264",
    "-pix_fmt", "yuv420p",
    "output/video.mp4"
])
print("✅ Xong! Xem file output/video.mp4")
EOF
```
Nếu cần lấy file về máy tính, copy về
```bash
# Chạy trên máy Windows (PowerShell)
scp aitek@<IP_PI>:~/camera_test/output/photo.jpg C:\Users\<user>\Downloads\
scp aitek@<IP_PI>:~/camera_test/output/video.mp4 C:\Users\<user>\Downloads\
```



