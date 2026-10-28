# Deploy lên AWS EC2 GPU (g6.xlarge), không dùng Docker

Chạy native trên Ubuntu: 2 venv (`paddlepaddle-gpu`) + 2 service systemd, tuỳ chọn Caddy làm HTTPS. Script cài đặt:
[`install.sh`](install.sh).

| | |
|---|---|
| Instance | `g6.xlarge`: 1 GPU NVIDIA L4 24GB, 4 vCPU, 16GB RAM, x86_64 |
| AMI | **Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04)** (đã có driver NVIDIA) |
| Ổ đĩa | ≥ 80GB gp3 (2 venv Paddle GPU + thư viện CUDA ~10GB, model ~3GB) |
| Service | `ocr-app` (cổng 8000, PP-OCR), `ocr-vl` (cổng 8011, PaddleOCR-VL, chỉ nghe 127.0.0.1), `caddy` (443, nếu có domain) |

## Vì sao không dùng Docker / khác gì trên Mac

- `requirements.txt` cài `paddlepaddle` bản **CPU**. Script đọc version đã pin trong đó (3.2.2 app, 3.3.1 vl_service) và cài
  `paddlepaddle-gpu` cùng version từ index của Paddle (`PADDLE_CUDA=cu126`, L4 cần CUDA 12). CUDA/cuDNN runtime đi kèm dạng
  gói pip `nvidia-*`, không cần cài CUDA toolkit; chỉ cần driver NVIDIA của AMI.
- App và vl_service vẫn là 2 venv riêng (2 bản Paddle khác nhau, lý do trong `CLAUDE.md`).
- Thiết bị chọn bằng `OCR_DEVICE` / `VL_DEVICE` (`gpu:0` | `cpu`); `/api/health` và `/health` của vl_service trả `device`
  để kiểm tra đang chạy GPU thật.

## 1. Tạo EC2

1. EC2 → Launch instance → AMI ở trên, type `g6.xlarge`, ổ 80GB, key pair của bạn.
   Tài khoản mới thường có quota GPU = 0: Service Quotas → *Running On-Demand G and VT instances* ≥ 4 vCPU.
2. Security Group:
   - `22` từ IP của bạn.
   - Có domain: `80` + `443` từ `0.0.0.0/0` (Let's Encrypt cần cổng 80).
   - **Không** mở `8000`/`8011` ra ngoài (API không có đăng nhập; ảnh thẻ là dữ liệu cá nhân).
3. Có domain: tạo bản ghi DNS `A` trỏ về Elastic IP của instance (gán Elastic IP để IP không đổi khi stop/start).

## 2. Lấy code lên máy

Repo private → dùng 1 trong 2:

```bash
# a) Deploy key chỉ đọc: ssh-keygen -t ed25519 trên EC2, thêm public key ở GitHub → repo → Settings → Deploy keys
git clone git@github.com:sonvc94/ocr.git ~/ocr

# b) gh CLI
sudo apt-get install -y gh && gh auth login && gh repo clone sonvc94/ocr ~/ocr
```

Không `rsync`/`scp` cả thư mục từ Mac: sẽ mang theo `logs/` và fixture thẻ thật (dữ liệu cá nhân, đã git-ignore).

## 3. Cài đặt

```bash
cd ~/ocr
nvidia-smi                                   # phải thấy "NVIDIA L4"
sudo ./deploy/aws-ec2-gpu/install.sh         # chỉ truy cập qua SSH tunnel
# hoặc HTTPS + mật khẩu:
sudo DOMAIN=ocr.example.com BASIC_AUTH_USER=demo BASIC_AUTH_PASSWORD='mật-khẩu' ./deploy/aws-ec2-gpu/install.sh
```

Lần đầu ~10–15 phút (tải Paddle GPU + model). Script:
1. Kiểm tra Ubuntu 24.04 + `nvidia-smi`.
2. Cài gói hệ thống (Python 3.12, libgl…).
3. Tạo `.venv` (app) và `vl_service/.venv`, cài `paddlepaddle-gpu`, chạy `paddle.utils.run_check()` (dừng nếu Paddle không thấy GPU).
4. Tải model vào `~/.paddlex` của user.
5. Tạo `/etc/ocr/ocr.env`, `/etc/ocr/vl.env` (chỉ khi chưa có; sửa tay được, chạy lại script không ghi đè).
6. Tạo + bật `ocr-app.service`, `ocr-vl.service`; nếu có `DOMAIN` thì cài Caddy (tự lấy chứng chỉ Let's Encrypt).
7. Gọi `/api/health`, cảnh báo nếu `device` không phải GPU.

Tuỳ chọn (biến môi trường khi chạy script):

| Biến | Mặc định | |
|---|---|---|
| `PADDLE_CUDA` | `cu126` | Index wheel Paddle: `cu118`, `cu126`, `cu129` |
| `INSTALL_VL` | `1` | `0` = không cài PaddleOCR-VL (`engine=vl` trả 503) |
| `APP_HOST` | `127.0.0.1` | `0.0.0.0` = mở cổng 8000 trực tiếp (không HTTPS → camera trong trang không chạy) |
| `DOMAIN` | | Có → cài Caddy làm HTTPS reverse proxy |
| `BASIC_AUTH_USER`, `BASIC_AUTH_PASSWORD` | | Có (cần `DOMAIN`) → Caddy hỏi mật khẩu |

Không có domain: `ssh -L 8000:127.0.0.1:8000 ubuntu@<IP>` rồi mở `http://localhost:8000` trên máy bạn
(localhost là secure context → camera trong trang vẫn chạy).

## 4. Kiểm tra

```bash
curl -s localhost:8000/api/health        # "device":"gpu:0"
curl -s localhost:8011/health            # "device":"gpu:0"
nvidia-smi                               # thấy 2 process python đang giữ bộ nhớ GPU
curl -s -F file=@samples/isa/residence_card_new_2026.jpg \
  "localhost:8000/api/extract?include_image=false&mode=hybrid" | python3 -m json.tool | grep -A4 timing_ms
```

`timing_ms.ocr` phải nhỏ hơn nhiều so với trên Mac CPU (~10 giây với model `server`). Request đầu sau khi khởi động
chậm hơn (khởi tạo CUDA kernel).

## 5. Vận hành

```bash
sudo systemctl status ocr-app ocr-vl
sudo systemctl restart ocr-app                     # sau khi sửa /etc/ocr/ocr.env
tail -f ~/ocr/logs/app.log ~/ocr/logs/vl_service.log
# cập nhật code
cd ~/ocr && git pull && sudo ./deploy/aws-ec2-gpu/install.sh   # hoặc chỉ restart nếu requirements không đổi
```

- Log: `logs/app.log`, `logs/vl_service.log` (trong thư mục project). `LOG_RESPONSES` / `DEBUG_SAVE_IMAGES` mặc định **tắt**
  trên server; bật trong `/etc/ocr/ocr.env` chỉ khi cần debug và xoá `logs/extract.jsonl`, `logs/images/` sau đó.
- GPU: L4 24GB đủ cho cả PP-OCR (~1–2GB) và PaddleOCR-VL. RAM 16GB là giới hạn khi nạp model lúc khởi động; tắt VL
  (`sudo systemctl disable --now ocr-vl`) nếu thiếu.
- Mỗi ngôn ngữ 1 instance model + lock → xử lý tuần tự từng request. Đủ cho demo.
- Chi phí: g6.xlarge tính theo giờ khi đang chạy → stop instance khi không dùng (ổ EBS vẫn tính phí).

## Lỗi thường gặp

| Triệu chứng | Cách xử lý |
|---|---|
| `nvidia-smi` lỗi | Sai AMI (không có driver) → dùng Deep Learning Base GPU AMI, hoặc cài `nvidia-driver-570` + reboot |
| `paddlepaddle is the CPU build` | Gói `paddlepaddle` CPU còn trong venv: `.venv/bin/pip uninstall paddlepaddle paddlepaddle-gpu` rồi chạy lại script |
| `libcudnn*.so not found` | Thiếu gói pip `nvidia-cudnn-cu12` → thử `PADDLE_CUDA` khác, hoặc cài cuDNN qua apt |
| `/api/health` trả `"device":"cpu"` | `OCR_DEVICE` trong `/etc/ocr/ocr.env` khác `gpu:0` |
| Caddy không lấy được chứng chỉ | DNS chưa trỏ đúng IP hoặc chưa mở cổng 80/443: `journalctl -u caddy` |
| `engine=vl` trả 503 | `ocr-vl` chưa chạy xong (nạp model mất vài phút) hoặc `INSTALL_VL=0`: xem `logs/vl_service.log` |
