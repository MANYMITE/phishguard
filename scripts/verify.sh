#!/usr/bin/env bash
# PhishGuard end-to-end verification script.
#
# Usage (from inside a phishguard checkout):
#     bash scripts/verify.sh
#
# What it does:
#   1. creates/uses a local .venv and installs dependencies
#   2. runs the full test suite
#   3. starts the server with a throwaway demo secret
#   4. drives the complete drill over HTTP: login -> CSRF -> campaign ->
#      participant -> personal link -> submit -> caught page -> stats
#   5. scans the database for the canary password (must be 0 hits)
#   6. stops the server and reports PASS/FAIL
set -euo pipefail
cd "$(dirname "$0")/.."

DEMO_SECRET="verify-demo-key-$$"
JAR="$(mktemp)"
LOG="$(mktemp)"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ✔ $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  ✘ $1"; }

cleanup() { [ -n "${SERVER_PID:-}" ] && kill "$SERVER_PID" 2>/dev/null || true; rm -f "$JAR" "$LOG"; }
trap cleanup EXIT

echo "== [1/5] test suite =="
if [ ! -d .venv ]; then python3 -m venv .venv; fi
. .venv/bin/activate
python -m pip install -q -r requirements.txt
if python -m unittest discover -s tests 2>&1 | tail -1 | grep -q OK; then
  ok "all tests pass"
else
  bad "test suite failed"; exit 1
fi

echo "== [2/5] start server =="
PHISHGUARD_SECRET_KEY="$DEMO_SECRET" PORT=5000 python run.py >"$LOG" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 30); do
  grep -q "Running on" "$LOG" 2>/dev/null && break
  sleep 0.5
done
grep -q "Running on" "$LOG" && ok "server is up on 127.0.0.1:5000" || { bad "server never started"; exit 1; }

get()  { curl -s -b "$JAR" -c "$JAR" "$@"; }
token() { get "$1" | grep -oE 'name="csrf_token" value="[^"]+"' | head -1 | sed 's/.*value="//;s/"//'; }

echo "== [3/5] admin flow =="
get http://127.0.0.1:5000/login > /dev/null
T1=$(token http://127.0.0.1:5000/login)
[ "$(get -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:5000/login -d "password=WRONG&csrf_token=$T1")" = "200" ] \
  && ok "wrong password rejected" || bad "wrong password accepted"
[ "$(get -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:5000/login -d "password=$DEMO_SECRET&csrf_token=$T1")" = "302" ] \
  && ok "login succeeds" || bad "login failed"
T2=$(token http://127.0.0.1:5000/)
[ -n "$T2" ] && ok "fresh CSRF token issued" || bad "no CSRF token"
get -o /dev/null -X POST http://127.0.0.1:5000/campaigns -d "name=Verify+drill&template_key=acme_webmail&consent=yes&csrf_token=$T2"
get http://127.0.0.1:5000/campaigns/1 | grep -q "created" && ok "campaign created" || bad "campaign missing"
get -o /dev/null -X POST http://127.0.0.1:5000/campaigns/1/participants -d "name=Demo&email=demo@example.com&consent=yes&csrf_token=$T2"
get http://127.0.0.1:5000/campaigns/1 | grep -q "demo@example.com" && ok "participant added" || bad "participant missing"

echo "== [4/5] participant flow =="
LINK=$(get http://127.0.0.1:5000/campaigns/1 | grep -oE 'http://127.0.0.1:5000/sim/1/[0-9]+-[A-Za-z0-9_-]+' | head -1)
[ -n "$LINK" ] && ok "personal tokenized link generated" || bad "no link found"
[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:5000/sim/1/1-forgedtoken")" = "404" ] \
  && ok "forged token returns 404" || bad "forged token accepted!"
curl -s "$LINK" | grep -q "Training exercise" && ok "honest banner shown" || bad "banner missing"
LOC=$(curl -s -o /dev/null -w '%{redirect_url}' -X POST "$LINK" -d "username=demo@example.com&password=VERIFY-CANARY-31337")
curl -s "$LOC" | grep -q "that was the drill" && ok "caught page reached" || bad "caught page broken"
get http://127.0.0.1:5000/campaigns/1 | grep -q "submitted the form" && ok "stats updated" || bad "stats missing"

echo "== [5/5] safety invariant on the live DB =="
if grep -q "VERIFY-CANARY-31337" phishguard.db 2>/dev/null; then
  bad "CANARY PASSWORD FOUND IN DB — invariant broken"
else
  ok "canary password never stored (0 hits)"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "✅ VERIFY PASSED ($PASS checks)"
  rm -f phishguard.db audit.log
  exit 0
else
  echo "❌ VERIFY FAILED ($FAIL of $((PASS+FAIL)) checks failed)"
  exit 1
fi
