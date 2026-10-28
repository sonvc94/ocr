#!/usr/bin/env bash
# Install the card OCR demo natively (no Docker) on an AWS EC2 GPU instance (g6.xlarge: NVIDIA L4).
#
# Expects Ubuntu 24.04 with the NVIDIA driver already installed (AMI "Deep Learning Base OSS Nvidia Driver
# GPU AMI (Ubuntu 24.04)"). Run from a checkout of the repo, as the user that owns it:
#
#   sudo ./deploy/aws-ec2-gpu/install.sh
#   sudo DOMAIN=ocr.example.com BASIC_AUTH_USER=demo BASIC_AUTH_PASSWORD='...' ./deploy/aws-ec2-gpu/install.sh
#
# Safe to re-run (e.g. after `git pull`): venvs are updated in place, /etc/ocr/*.env is kept if it exists.
# See deploy/aws-ec2-gpu/README.md.
set -euo pipefail

PADDLE_CUDA="${PADDLE_CUDA:-cu126}"       # Paddle wheel index: cu118 | cu126 | cu129 (the L4 needs CUDA 12)
INSTALL_VL="${INSTALL_VL:-1}"             # 1 = also install PaddleOCR-VL (engine=vl) as ocr-vl.service
APP_HOST="${APP_HOST:-127.0.0.1}"         # 0.0.0.0 = reach port 8000 directly (no HTTPS: in-page camera won't work)
DOMAIN="${DOMAIN:-}"                      # set = install Caddy as HTTPS reverse proxy (Let's Encrypt) for this domain
BASIC_AUTH_USER="${BASIC_AUTH_USER:-}"    # set both = Caddy asks for a password (the API has no auth of its own)
BASIC_AUTH_PASSWORD="${BASIC_AUTH_PASSWORD:-}"

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_USER="${SUDO_USER:-$(stat -c %U "$APP_DIR")}"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
PADDLE_INDEX="https://www.paddlepaddle.org.cn/packages/stable/${PADDLE_CUDA}/"
ENV_DIR=/etc/ocr

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
as_user() { sudo -u "$RUN_USER" -H env PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True "$@"; }

[[ $EUID -eq 0 ]] || die "run with sudo"
[[ "$RUN_USER" != root ]] || die "run as a normal user with sudo (services must not run as root)"
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || die "needs Ubuntu 24.04 (found $PRETTY_NAME)"
command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null \
  || die "nvidia-smi fails: use the Deep Learning Base GPU AMI or install the NVIDIA driver first"
if [[ -n "$BASIC_AUTH_USER" && -z "$DOMAIN" ]]; then die "BASIC_AUTH_* needs DOMAIN (Caddy)"; fi

log "System packages"
apt-get update -q
apt-get install -y -q python3.12 python3.12-venv python3-pip libgl1 libglib2.0-0 libgomp1 curl

# Pinned paddlepaddle version from a requirements file, installed as paddlepaddle-gpu from Paddle's index
# (the GPU wheels are not on PyPI); the CUDA/cuDNN runtime comes as nvidia-* pip packages.
make_venv() {  # <dir> <requirements.txt>
  local dir="$1" req="$2" ver
  ver="$(sed -n 's/^paddlepaddle==\([0-9.]*\).*/\1/p' "$req")"
  [[ -n "$ver" ]] || die "no paddlepaddle pin in $req"
  [[ -x "$dir/.venv/bin/python" ]] || as_user python3.12 -m venv "$dir/.venv"
  as_user "$dir/.venv/bin/pip" install -q --upgrade pip
  as_user "$dir/.venv/bin/pip" install -q "paddlepaddle-gpu==$ver" \
    --index-url https://pypi.org/simple --extra-index-url "$PADDLE_INDEX"
  as_user "$dir/.venv/bin/pip" uninstall -y -q paddlepaddle 2>/dev/null || true  # CPU build would shadow the GPU one
  grep -v '^paddlepaddle==' "$req" > "$dir/.venv/requirements-gpu.txt"
  chown "$RUN_USER:" "$dir/.venv/requirements-gpu.txt"
  as_user "$dir/.venv/bin/pip" install -q -r "$dir/.venv/requirements-gpu.txt"
  log "Check Paddle sees the GPU ($dir)"
  as_user "$dir/.venv/bin/python" -c "
import paddle
assert paddle.device.is_compiled_with_cuda(), 'paddlepaddle is the CPU build'
assert paddle.device.cuda.device_count() > 0, 'no GPU visible to Paddle'
print(paddle.__version__, paddle.device.cuda.get_device_name(0))
paddle.utils.run_check()"
}

log "App venv (PP-OCR, paddlepaddle-gpu from requirements.txt)"
make_venv "$APP_DIR" "$APP_DIR/requirements.txt"
as_user mkdir -p "$APP_DIR/logs"

log "Download PP-OCR models (~/.paddlex of $RUN_USER)"
(cd "$APP_DIR" && as_user OCR_DEVICE=gpu:0 "$APP_DIR/.venv/bin/python" -m scripts.download_models)

if [[ "$INSTALL_VL" == 1 ]]; then
  log "vl_service venv (PaddleOCR-VL)"
  make_venv "$APP_DIR/vl_service" "$APP_DIR/vl_service/requirements.txt"
  log "Download PaddleOCR-VL model"
  (cd "$APP_DIR/vl_service" && as_user VL_DEVICE=gpu:0 "$APP_DIR/vl_service/.venv/bin/python" \
    -c "import main; main.get_vl(); print('models ready')")
fi

log "Config in $ENV_DIR (kept if it exists)"
mkdir -p "$ENV_DIR"
if [[ ! -f "$ENV_DIR/ocr.env" ]]; then
  cat > "$ENV_DIR/ocr.env" <<EOF
OCR_DEVICE=gpu:0
OCR_MODEL_SIZE=server
# 1 = log full results / save uploaded images to logs/ (personal data from the cards)
LOG_RESPONSES=0
DEBUG_SAVE_IMAGES=0
VL_URL=http://127.0.0.1:8011
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
EOF
fi
if [[ ! -f "$ENV_DIR/vl.env" ]]; then
  cat > "$ENV_DIR/vl.env" <<EOF
VL_DEVICE=gpu:0
VL_PIPELINE_VERSION=v1.5
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
EOF
fi
chmod 644 "$ENV_DIR"/*.env

log "systemd services"
cat > /etc/systemd/system/ocr-app.service <<EOF
[Unit]
Description=Card OCR demo (FastAPI, PP-OCR)
After=network-online.target
Wants=network-online.target

[Service]
User=$RUN_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_DIR/ocr.env
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host $APP_HOST --port 8000
StandardOutput=append:$APP_DIR/logs/app.log
StandardError=append:$APP_DIR/logs/app.log
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
if [[ "$INSTALL_VL" == 1 ]]; then
  cat > /etc/systemd/system/ocr-vl.service <<EOF
[Unit]
Description=PaddleOCR-VL service for the card OCR demo
After=network-online.target
Wants=network-online.target

[Service]
User=$RUN_USER
WorkingDirectory=$APP_DIR/vl_service
EnvironmentFile=$ENV_DIR/vl.env
ExecStart=$APP_DIR/vl_service/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8011
StandardOutput=append:$APP_DIR/logs/vl_service.log
StandardError=append:$APP_DIR/logs/vl_service.log
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
fi
systemctl daemon-reload
systemctl enable ocr-app
systemctl restart ocr-app
if [[ "$INSTALL_VL" == 1 ]]; then systemctl enable ocr-vl; systemctl restart ocr-vl; fi

if [[ -n "$DOMAIN" ]]; then
  log "Caddy (HTTPS for $DOMAIN)"
  if ! command -v caddy >/dev/null; then
    apt-get install -y -q debian-keyring debian-archive-keyring apt-transport-https gnupg
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
      | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -q
    apt-get install -y -q caddy
  fi
  auth=""
  if [[ -n "$BASIC_AUTH_USER" ]]; then
    [[ -n "$BASIC_AUTH_PASSWORD" ]] || die "BASIC_AUTH_PASSWORD is empty"
    hash="$(caddy hash-password --plaintext "$BASIC_AUTH_PASSWORD")"
    auth=$'\tbasic_auth {\n\t\t'"$BASIC_AUTH_USER $hash"$'\n\t}\n'
  fi
  cat > /etc/caddy/Caddyfile <<EOF
$DOMAIN {
	request_body {
		max_size 12MB
	}
${auth}	reverse_proxy 127.0.0.1:8000
}
EOF
  systemctl enable caddy
  systemctl reload-or-restart caddy
fi

log "Wait for the app to load the models"
for _ in $(seq 60); do
  if health="$(curl -sf http://127.0.0.1:8000/api/health)"; then break; fi
  sleep 5
done
[[ -n "${health:-}" ]] || die "app did not start, see $APP_DIR/logs/app.log"
echo "$health"
[[ "$health" == *'"device":"gpu'* ]] || echo "WARNING: the app is not running on the GPU"
if [[ "$INSTALL_VL" == 1 ]]; then
  for _ in $(seq 60); do
    if vl="$(curl -sf http://127.0.0.1:8011/health)"; then echo "$vl"; break; fi
    sleep 5
  done
  [[ -n "${vl:-}" ]] || echo "WARNING: ocr-vl not up yet, see $APP_DIR/logs/vl_service.log"
fi

log "Done"
if [[ -n "$DOMAIN" ]]; then echo "Open https://$DOMAIN"
elif [[ "$APP_HOST" == 127.0.0.1 ]]; then echo "From your machine: ssh -L 8000:127.0.0.1:8000 $RUN_USER@<EC2 IP>, then http://localhost:8000"
else echo "Open http://<EC2 public IP>:8000"
fi
