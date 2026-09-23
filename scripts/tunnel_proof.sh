#!/usr/bin/env bash
# Atomic tunnel proof: launch share.sh pinggy, then drill the PUBLIC URL
# from the same session (real round trip through Pinggy's relay).
set -u
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

pkill -f "python run.py" 2>/dev/null; pkill -f pinggy 2>/dev/null; sleep 1
export PHISHGUARD_SECRET_KEY="${PHISHGUARD_SECRET_KEY:-tunnel-demo-key}"
rm -f share-run.log tunnel.log
setsid nohup bash scripts/share.sh pinggy > share-run.log 2>&1 &
sleep 2

# Wait for the tunnel URL (Pinggy uses several free domains).
URL=""
for _ in $(seq 1 40); do
  URL=$(grep -hoE 'https://[a-z0-9.-]+(pinggy-free\.link|free\.pinggy\.net|pinggy\.link)[^ ]*' \
        tunnel.log share-run.log 2>/dev/null | grep -v Dashboard | head -1)
  [ -n "$URL" ] && break
  sleep 1
done
if [ -z "$URL" ]; then
  echo "FAIL: no tunnel URL appeared"; tail -5 tunnel.log 2>/dev/null; exit 1
fi
echo "TUNNEL_URL=$URL"
sleep 3

JAR=$(mktemp)
# Retry up to 3x: the first request through a fresh tunnel often times out.
G() {
  local out="" i=0
  while [ $i -lt 3 ]; do
    out=$(curl -s --max-time 25 -b "$JAR" -c "$JAR" "$@")
    [ -n "$out" ] && break
    i=$((i+1)); sleep 1
  done
  printf '%s' "$out"
}
T() { G "$1" | grep -oE 'name="csrf_token" value="[^"]+"' | head -1 | sed 's/.*value="//;s/"//'; }
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✔ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✘ $1"; }

echo "== drilling the PUBLIC url from inside this session =="
[ "$(G "$URL/health" | head -c 30)" = '{"app":"phishguard","status":"ok"}' ] \
  && ok "health via public internet" || bad "health via public internet"

T1=$(T "$URL/login")
G -o /dev/null -X POST "$URL/login" -d "password=WRONG&csrf_token=$T1"
G "$URL/login" | grep -q "Wrong admin password" && ok "wrong password rejected" || bad "wrong password rejected"
[ "$(G -o /dev/null -w '%{http_code}' -X POST "$URL/login" -d "password=$PHISHGUARD_SECRET_KEY&csrf_token=$T1")" = "302" ] \
  && ok "admin login via public url" || bad "admin login via public url"

T2=$(T "$URL/")
[ -n "$T2" ] && ok "fresh CSRF token" || bad "fresh CSRF token"
G -o /dev/null -X POST "$URL/campaigns" -d "name=Tunnel+proof&template_key=acme_webmail&consent=yes&csrf_token=$T2"
# Campaign id depends on whether earlier test data survived; detect it.
CID=""
for id in 1 2 3 4 5; do
  if G "$URL/campaigns/$id" | grep -q "Tunnel proof"; then CID=$id; break; fi
done
[ -n "$CID" ] && ok "campaign created (#$CID)" || bad "campaign created"
G -o /dev/null -X POST "$URL/campaigns/$CID/participants" -d "name=Remote&email=remote@example.com&consent=yes&csrf_token=$T2"
PAGE=$(G "$URL/campaigns/$CID")
LINK=$(echo "$PAGE" | grep -oE "$URL/sim/$CID/[0-9]+-[A-Za-z0-9_-]+" | head -1)
[ -n "$LINK" ] && ok "participant link carries public host" || bad "participant link missing"

PID_NUM=$(echo "$LINK" | grep -oE "[0-9]+" | head -1)
[ "$(curl -s --max-time 25 -o /dev/null -w '%{http_code}' "$URL/sim/$CID/$PID_NUM-forged")" = "404" ] \
  && ok "forged token 404 via public url" || bad "forged token 404 via public url"
G "$LINK" | grep -q "Training exercise" && ok "honest banner via public url" || bad "honest banner missing"
LOC=$(G -o /dev/null -w '%{redirect_url}' -X POST "$LINK" -d "username=remote@example.com&password=PROOF-CANARY-1")
G "$LOC" | grep -q "that was the drill" && ok "caught page via public url" || bad "caught page broken"
G "$URL/campaigns/$CID" | grep -q "submitted the form" && ok "stats via public url" || bad "stats missing"

if grep -q "PROOF-CANARY-1" phishguard.db 2>/dev/null; then
  bad "canary stored (invariant broken!)"
else
  ok "canary never stored (0 hits)"
fi

rm -f "$JAR"
echo
[ "$FAIL" -eq 0 ] && echo "✅ TUNNEL PROOF PASSED ($PASS checks) — $URL" || echo "❌ TUNNEL PROOF FAILED ($FAIL)"
[ "$FAIL" -eq 0 ] || exit 1
