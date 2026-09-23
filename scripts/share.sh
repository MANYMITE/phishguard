#!/usr/bin/env bash
# PhishGuard tunnel launcher — make your drill reachable from any network.
#
# Usage:
#     bash scripts/share.sh              # auto: cloudflared → pinggy → ngrok → localtunnel
#     bash scripts/share.sh cloudflare   # quick tunnel, no account needed
#     bash scripts/share.sh pinggy       # SSH-over-443 tunnel, no account (great on
#                                        # networks that block QUIC/7844 or flaky relays)
#     bash scripts/share.sh ngrok        # needs ngrok + NGROK_AUTHTOKEN
#     bash scripts/share.sh localtunnel  # uses the local lt binary via npx
#     bash scripts/share.sh lan          # LAN only (0.0.0.0), no tunnel
#
# Env vars:
#   TUNNEL_PROTOCOL=http2   force cloudflared onto TCP (use on networks that
#                           block QUIC/UDP — symptom: Cloudflare error 1033)
#
# What it does:
#   1. picks an available tunnel tool (or installs cloudflared with consent)
#   2. starts PhishGuard bound to localhost
#   3. starts the tunnel and scrapes the public https URL
#   4. prints your admin panel and the base URL to use in participant links
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-auto}"
PORT="${PORT:-5000}"
# Tunnels serve HTTPS: mark session cookies Secure. (LAN mode overrides.)
export PHISHGUARD_FORCES_HTTPS=1

have() { command -v "$1" >/dev/null 2>&1; }

activate_venv() {
  if [ -d .venv ]; then . .venv/bin/activate
  else
    echo "[*] Creating virtual environment..."
    python3 -m venv .venv
    . .venv/bin/activate
    python -m pip install -q -r requirements.txt
  fi
}

# Fully detach background jobs from the launching terminal/session so the
# tunnel survives (setsid is the reliable way; plain nohup can get HUP'd
# through process trees in WSL and some shells).
run_detached() {
  if have setsid; then
    setsid nohup "$@" &
  else
    nohup "$@" &
  fi
}

if [ -z "${PHISHGUARD_SECRET_KEY:-}" ]; then
  echo "✖ Set PHISHGUARD_SECRET_KEY first (it is the admin password)."
  echo "    export PHISHGUARD_SECRET_KEY=\"a-long-random-string\""
  exit 1
fi

activate_venv
echo "[*] Starting PhishGuard on 127.0.0.1:$PORT ..."
PHISHGUARD_BEHIND_PROXY=1 PORT="$PORT" run_detached python run.py > phishguard-server.log 2>&1
APP_PID=$!
trap '[ -n "${TUNNEL_PID:-}" ] && kill "$TUNNEL_PID" 2>/dev/null || true; kill "$APP_PID" 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do grep -q "Running on" phishguard-server.log 2>/dev/null && break; sleep 0.5; done
grep -q "Running on" phishguard-server.log || { echo "✖ App failed to start:"; tail -5 phishguard-server.log; exit 1; }
echo "[✓] Admin panel:  http://127.0.0.1:$PORT"

print_urls() {
  echo
  echo "==============================================================="
  echo "  Public admin panel : $1"
  echo "  Participant links  : create them in the panel — they will"
  echo "                       automatically use this public host."
  echo "  Stop everything    : Ctrl+C (tunnel and server shut down)"
  echo "  The admin panel is now on the public internet — keep the"
  echo "  secret key strong and close the tunnel when done."
  echo "==============================================================="
}

install_cloudflared() {
  echo "[*] cloudflared not found. Install it now?"
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" ;;
    Linux-aarch64) URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64" ;;
    MINGW*|MSYS*|Darwin) echo "  On Windows/macOS: brew install cloudflared  (or winget install Cloudflare.cloudflared)"; return 1 ;;
    *) return 1 ;;
  esac
  read -r -p "  Download to ~/.local/bin? [y/N] " REPLY
  case "$REPLY" in
    [yY]*)
      mkdir -p ~/.local/bin
      curl -sL "$URL" -o ~/.local/bin/cloudflared && chmod +x ~/.local/bin/cloudflared
      export PATH="$HOME/.local/bin:$PATH"; have cloudflared; ;;
    *) return 1 ;;
  esac
}

start_tunnel() {
  case "$MODE" in
    cloudflare|auto)
      have cloudflared || install_cloudflared || true
      if have cloudflared; then
        echo "[*] Starting Cloudflare quick tunnel (no account needed)..."
        # TUNNEL_PROTOCOL=http2 helps on networks where QUIC/UDP is blocked
        # (symptom: Cloudflare error 1033, 'failed to dial ... quic').
        nohup cloudflared tunnel --url "http://127.0.0.1:$PORT" --no-autoupdate \
          ${TUNNEL_PROTOCOL:+--protocol "$TUNNEL_PROTOCOL"} > tunnel.log 2>&1 &
        TUNNEL_PID=$!
        for _ in $(seq 1 60); do grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" tunnel.log 2>/dev/null | head -1 | grep -q . && break; sleep 1; done
        URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" tunnel.log | head -1)
        [ -n "$URL" ] && { print_urls "$URL"; wait; return; }
        echo "[!] Cloudflare tunnel failed:"; tail -3 tunnel.log
        [ "$MODE" = "cloudflare" ] && exit 1
      elif [ "$MODE" = "cloudflare" ]; then
        exit 1
      fi
      ;;&
    pinggy|auto)
      if have ssh; then
        echo "[*] Starting Pinggy tunnel (SSH over port 443, no account)..."
        run_detached ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 \
          -p 443 -R0:localhost:$PORT a.pinggy.io > tunnel.log 2>&1
        TUNNEL_PID=$!
        for _ in $(seq 1 30); do grep -oE "https://[a-z0-9.-]+\.free\.pinggy\.link" tunnel.log 2>/dev/null | head -1 | grep -q . && break; sleep 1; done
        URL=$(grep -oE "https://[a-z0-9.-]+\.free\.pinggy\.link" tunnel.log | head -1)
        [ -n "$URL" ] && { print_urls "$URL"; wait; return; }
        echo "[!] Pinggy failed:"; tail -3 tunnel.log
        [ "$MODE" = "pinggy" ] && exit 1
      elif [ "$MODE" = "pinggy" ]; then
        echo "✖ ssh client not found."; exit 1
      fi
      ;;&
    ngrok|auto)
      if have ngrok; then
        echo "[*] Starting ngrok tunnel..."
        [ -n "${NGROK_AUTHTOKEN:-}" ] && ngrok config add-authtoken "$NGROK_AUTHTOKEN" >/dev/null 2>&1 || true
        nohup ngrok http "$PORT" --log stdout > tunnel.log 2>&1 &
        TUNNEL_PID=$!
        for _ in $(seq 1 30); do grep -q "url" tunnel.log 2>/dev/null && break; sleep 1; done
        URL=$(grep -oE "https://[a-z0-9-]+\.(ngrok-free\.app|ngrok\.io)" tunnel.log | head -1)
        [ -z "$URL" ] && URL=$(curl -s http://127.0.0.1:4040/api/tunnels | grep -oE 'https://[a-z0-9-]+\.(ngrok-free\.app|ngrok\.io)' | head -1 || true)
        [ -n "$URL" ] && { print_urls "$URL"; wait; return; }
        echo "[!] ngrok failed:"; tail -3 tunnel.log
        [ "$MODE" = "ngrok" ] && exit 1
      elif [ "$MODE" = "ngrok" ]; then
        echo "✖ ngrok not installed. Install from https://ngrok.com/download"; exit 1
      fi
      ;;&
    localtunnel|auto)
      if have lt || have npx; then
        echo "[*] Starting localtunnel..."
        if have lt; then
          run_detached lt --port "$PORT" > tunnel.log 2>&1
          TUNNEL_PID=$!
        else
          run_detached npx -y localtunnel --port "$PORT" > tunnel.log 2>&1
          TUNNEL_PID=$!
        fi
        for _ in $(seq 1 30); do grep -oE "https://[a-z0-9-]+\.loca\.lt" tunnel.log 2>/dev/null | head -1 | grep -q . && break; sleep 1; done
        URL=$(grep -oE "https://[a-z0-9-]+\.loca\.lt" tunnel.log | head -1)
        [ -n "$URL" ] && { echo; echo "[i] localtunnel may show a tunnel-password page"; echo "    (visitors enter your public IP once)."; print_urls "$URL"; wait; return; }
        echo "[!] localtunnel failed:"; tail -3 tunnel.log
        [ "$MODE" = "localtunnel" ] && exit 1
      fi
      ;;&
    lan)
      echo "[*] LAN mode: restarting app on 0.0.0.0 ..."
      export PHISHGUARD_FORCES_HTTPS=0  # plain HTTP: keep cookies usable
      kill "$APP_PID" 2>/dev/null || true
      PHISHGUARD_BEHIND_PROXY=1 PHISHGUARD_HOST=0.0.0.0 PORT="$PORT" run_detached python run.py > phishguard-server.log 2>&1
      APP_PID=$!
      IP=$(hostname -I 2>/dev/null | awk '{print $1}')
      [ -z "$IP" ] && IP="<your-machine-ip>"
      print_urls "http://$IP:$PORT"
      wait; return
      ;;
  esac
  echo "✖ No tunnel method available."
  echo "   Try:  bash scripts/share.sh cloudflare   (offers a one-time install)"
  exit 1
}

start_tunnel
