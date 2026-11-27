#!/usr/bin/env bash
# Mission 1 acceptance tests for the Northgate voice webhook.
#
# Needs two values, read from mission1/.env (never commit it) or the environment:
#   N8N_VOICE_URL  the workflow's production webhook URL
#   N8N_DESK_KEY   the value you put in the "Northgate desk key" Header Auth credential
#
# Usage: ./test-mission1.sh
set -u
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
: "${N8N_VOICE_URL:?Set N8N_VOICE_URL in mission1/.env}"
: "${N8N_DESK_KEY:?Set N8N_DESK_KEY in mission1/.env}"

FIX=fixtures
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
pass=0; fail=0
ok()  { echo "  PASS  $1"; pass=$((pass+1)); }
bad() { echo "  FAIL  $1"; fail=$((fail+1)); }
skip() { echo "  SKIP  $1"; }
auth_off() { [ "${DESK_AUTH:-key}" = none ]; }

# ---------- fixtures ----------
mkdir -p "$FIX"
if [ ! -f "$FIX/hello.m4a" ]; then
  say -o "$OUT/hello.aiff" "Hello, I would like to book a physio appointment for next Tuesday morning."
  afconvert -f mp4f -d aac "$OUT/hello.aiff" "$FIX/hello.m4a"          # what Safari / the iPad sends
  ffmpeg -loglevel error -y -i "$FIX/hello.m4a" -c:a libopus "$FIX/hello.webm"   # what Chrome sends
fi
: > "$FIX/empty.webm"
[ -f "$FIX/too-big.webm" ] || head -c 6000000 /dev/urandom > "$FIX/too-big.webm"

# post <label> <outfile> [curl args...] -> prints "status content_type seconds"
post() {
  local out=$1; shift
  curl -s -o "$out" -w '%{http_code} %{content_type} %{time_total}' -X POST "$N8N_VOICE_URL" "$@"
}

echo "Mission 1 acceptance tests -> ${N8N_VOICE_URL%%/webhook*}/webhook/…"

# 1. No key
if auth_off; then skip "no key / wrong key refused (DESK_AUTH=none)"; else
read -r code _ _ < <(post "$OUT/r1" -F "audio=@$FIX/hello.webm")
[[ $code == 401 || $code == 403 ]] && ok "no key is refused ($code)" || bad "no key should be 401/403, got $code"

# 2. Wrong key
read -r code _ _ < <(post "$OUT/r2" -H "X-Desk-Key: wrong-key" -F "audio=@$FIX/hello.webm")
[[ $code == 401 || $code == 403 ]] && ok "wrong key is refused ($code)" || bad "wrong key should be 401/403, got $code"

fi

# 3. No audio field
read -r code ctype _ < <(post "$OUT/r3" -H "X-Desk-Key: $N8N_DESK_KEY" -F "note=hello")
[[ $code == 400 && $ctype == application/json* ]] && grep -q '"error"' "$OUT/r3" \
  && ok "missing audio -> 400 JSON: $(cat "$OUT/r3")" || bad "missing audio should be 400 JSON, got $code $ctype $(head -c 200 "$OUT/r3")"

# 4. Empty recording
read -r code ctype _ < <(post "$OUT/r4" -H "X-Desk-Key: $N8N_DESK_KEY" -F "audio=@$FIX/empty.webm;type=audio/webm")
[[ $code == 400 && $ctype == application/json* ]] && grep -q '"error"' "$OUT/r4" \
  && ok "empty recording -> 400 JSON: $(cat "$OUT/r4")" || bad "empty recording should be 400 JSON, got $code $ctype $(head -c 200 "$OUT/r4")"

# 5. Over 5 MB
read -r code ctype _ < <(post "$OUT/r5" -H "X-Desk-Key: $N8N_DESK_KEY" -F "audio=@$FIX/too-big.webm;type=audio/webm")
[[ $code == 400 && $ctype == application/json* ]] && grep -q '"error"' "$OUT/r5" \
  && ok "6 MB recording -> 400 JSON: $(cat "$OUT/r5")" || bad "6 MB recording should be 400 JSON, got $code $ctype $(head -c 200 "$OUT/r5")"

# 6 + 7. Real speech, Chrome format and Safari format
for f in hello.webm hello.m4a; do
  type=audio/webm; [[ $f == *.m4a ]] && type=audio/mp4
  read -r code ctype secs < <(post "$OUT/r_$f" -H "X-Desk-Key: $N8N_DESK_KEY" -H "X-Request-Id: test-$f-$$" -F "audio=@$FIX/$f;type=$type")
  size=$(wc -c < "$OUT/r_$f" | tr -d ' ')
  if [[ $code == 200 && $ctype == audio/* && $size -gt 2000 ]]; then
    ok "$f ($type) -> spoken reply, $size bytes, ${secs}s"
    awk "BEGIN{exit !($secs < 4)}" && ok "$f reply under 4 s (${secs}s)" || bad "$f reply took ${secs}s, target is under 4 s"
  else
    bad "$f should return audio, got $code $ctype $size bytes: $(head -c 200 "$OUT/r_$f")"
  fi
done

# 8. Browser preflight: the recorder page (opened from a file, origin "null") must be allowed to send the key header
hdrs=$(curl -s -o /dev/null -D - -X OPTIONS "$N8N_VOICE_URL" -H "Origin: null" \
  -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: x-desk-key,x-request-id")
echo "$hdrs" | grep -qi '^access-control-allow-origin:' && echo "$hdrs" | grep -i '^access-control-allow-headers:' | grep -qi 'x-desk-key' \
  && ok "browser preflight allows the X-Desk-Key header" || bad "browser preflight does not allow X-Desk-Key: $(echo "$hdrs" | grep -i '^access-control' | tr '\r\n' '  ')"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
