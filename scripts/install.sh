#!/usr/bin/env bash
# One-command install of the Metachlorian core on a Linux/macOS server or NAS.
#
#   curl -fsSL https://raw.githubusercontent.com/JeremySNR/Metachlorian/main/scripts/install.sh | bash
#
# Options (environment variables):
#   METACHLORIAN_MODE=docker|native   default: docker when available, else native
#   METACHLORIAN_DATA=/srv/metachlorian   library location
#   FOOTAGE_DIR=/path/to/footage          folder to watch (docker mode)
set -euo pipefail
MODE="${METACHLORIAN_MODE:-}"
DATA="${METACHLORIAN_DATA:-$HOME/.local/share/metachlorian}"
REPO="${METACHLORIAN_REPO:-https://github.com/JeremySNR/Metachlorian.git}"
SRC="${METACHLORIAN_SRC:-$HOME/.local/src/metachlorian}"
say() { printf '\033[1m==> %s\033[0m\n' "$*"; }

if [ -z "$MODE" ]; then
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then MODE=docker; else MODE=native; fi
fi
say "Installing Metachlorian ($MODE mode)"
if [ ! -d "$SRC/.git" ]; then git clone --depth 1 "$REPO" "$SRC"; else git -C "$SRC" pull --ff-only; fi

if [ "$MODE" = docker ]; then
  if [ -z "${METACHLORIAN_ADMIN_PASSWORD:-}" ]; then
    METACHLORIAN_ADMIN_PASSWORD="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 20)"
    say "Generated admin password: $METACHLORIAN_ADMIN_PASSWORD  (user: admin)"
  fi
  export METACHLORIAN_ADMIN_PASSWORD FOOTAGE_DIR="${FOOTAGE_DIR:-$HOME/Footage}"
  docker compose -f "$SRC/deploy/docker-compose.yml" up -d --build
  say "Open http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo localhost):8765"
  exit 0
fi

command -v ffmpeg >/dev/null || { echo "Please install FFmpeg first (apt install ffmpeg / brew install ffmpeg)"; exit 1; }
if ! command -v uv >/dev/null; then curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; fi
uv venv -q -p 3.11 "$SRC/.venv"
uv pip install -q -p "$SRC/.venv/bin/python" "$SRC/core[analysis,s3]"
BIN="$SRC/.venv/bin/metachlorian"
"$BIN" --data "$DATA" init
"$BIN" --data "$DATA" models fetch || say "Some models failed to download; re-run: $BIN models fetch"
if command -v npm >/dev/null; then (cd "$SRC/app" && npm ci --no-audit --no-fund && npm run build) || say "Web app build failed; the API still works."; fi
if command -v systemctl >/dev/null && [ "$(id -u)" != 0 ]; then
  mkdir -p "$HOME/.config/systemd/user"
  cat > "$HOME/.config/systemd/user/metachlorian.service" <<UNIT
[Unit]
Description=Metachlorian core
After=network-online.target
[Service]
ExecStart=$BIN --data $DATA serve
Restart=on-failure
[Install]
WantedBy=default.target
UNIT
  systemctl --user daemon-reload && systemctl --user enable --now metachlorian
  say "Running as a user service: systemctl --user status metachlorian"
else
  say "Start it with: $BIN --data $DATA serve --add ~/Footage"
fi
say "Solo mode listens on http://127.0.0.1:8765. For team mode see docs/deployment.md."
