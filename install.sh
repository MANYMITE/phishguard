#!/usr/bin/env bash
# PhishGuard installer — works on apt, dnf, pacman and zypper distros.
set -euo pipefail

cd "$(dirname "$0")"

have() { command -v "$1" >/dev/null 2>&1; }

SUDO=""
if [ "$(id -u)" -ne 0 ] && have sudo; then SUDO="sudo"; fi

install_pkgs() {
    if have apt-get; then
        $SUDO apt-get update -qq
        $SUDO apt-get install -y python3 python3-venv python3-pip
    elif have dnf; then
        $SUDO dnf install -y python3 python3-pip
    elif have pacman; then
        $SUDO pacman -Sy --noconfirm python python-pip
    elif have zypper; then
        $SUDO zypper --non-interactive install python3 python3-pip
    else
        echo "ERROR: no supported package manager found (apt/dnf/pacman/zypper)." >&2
        echo "Install Python 3 + venv manually, then re-run this script." >&2
        exit 1
    fi
}

if ! have python3; then
    echo "[*] Installing Python 3 ..."
    install_pkgs
fi

echo "[*] Creating virtual environment (.venv) ..."
python3 -m venv .venv

echo "[*] Installing dependencies ..."
. .venv/bin/activate
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt

echo
echo "✅ Done. Start PhishGuard with:"
echo "     . .venv/bin/activate"
echo "     python run.py"
echo "   then open http://127.0.0.1:5000"
