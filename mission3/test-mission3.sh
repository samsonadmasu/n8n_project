#!/usr/bin/env bash
# Mission 3 acceptance tests: things break, and the caller and the staff both know what happened.
#
# Failures are simulated with the X-Simulate-Failure header (tts | agent). The workflow only
# honours it for sessions whose id starts with "test-", so real callers can't trigger it.
# Each simulated failure also sends a real Pushover alert to staff.
set -u
cd "$(dirname "$0")"
[ -f ../mission1/.env ] && set -a && . ../mission1/.env && set +a
: "${N8N_VOICE_URL:?Set N8N_VOICE_URL in mission1/.env}"
TOOLS="${N8N_VOICE_URL%%/webhook/*}/webhook/northgate-tools"
AUTH=(); [ "${DESK_AUTH:-key}" != none ] && AUTH=(-H "X-Desk-Key: ${N8N_DESK_KEY:?}")

read -r DAY SPOKEN < <(python3 -I -c '
import datetime as d
w=d.date.today()+d.timedelta(days=16)
while w.weekday()>4: w+=d.timedelta(days=1)
print(w, w.strftime("%A")+"_"+str(w.day)+"_"+w.strftime("%B"))')
SPOKEN=${SPOKEN//_/ }
RUN=$$
OUT=$(mktemp -d)
pass=0; fail=0
ok()  { echo "  PASS  $1"; pass=$((pass+1)); }
bad() { echo "  FAIL  $1"; fail=$((fail+1)); }
hdr() { grep -i "^$1:" "$OUT/h" | cut -d' ' -f2- | tr -d '\r' | python3 -I -c 'import sys,urllib.parse;print(urllib.parse.unquote(sys.stdin.read().strip()))'; }

# turn <session> <message> [extra curl args] -> sets CODE CTYPE SECS ROUTE REPLY
turn() {
  local s=$1 m=$2; shift 2
  read -r CODE CTYPE SECS < <(curl -s -o "$OUT/b" -D "$OUT/h" -w '%{http_code} %{content_type} %{time_total}\n' \
    -X POST "$N8N_VOICE_URL" ${AUTH[@]+"${AUTH[@]}"} -H "X-Session-Id: $s" "$@" -F "message=$m")
  ROUTE=$(hdr x-route); REPLY=$(hdr x-reply-text)
  echo "        you: $m"
  echo "        bot: ${REPLY:-<none>} [$CODE ${CTYPE%%;*} route=${ROUTE:-?} degraded=$(hdr x-degraded) alerted=$(hdr x-alerted) ${SECS}s]"
}
tool() { curl -s -X POST "$TOOLS/$1" ${AUTH[@]+"${AUTH[@]}"} -H 'Content-Type: application/json' -d "$2"; }
field() { python3 -I -c "import json,sys; d=json.loads(sys.argv[1]); print(eval(sys.argv[2]))" "$1" "$2" 2>/dev/null; }
cleanup() {
  # n8n Cloud limits how many runs execute at once, so cancel 4 at a time, not all at once.
  local p t h
  for p in +10000000030 +10000000031 +10000000032 +10000000033 +10000000034; do
    for t in Amina Daniel Sara; do
      for h in 09 10 11 12 13 14 15 16; do
        printf '{"phone":"%s","date":"%s","time":"%s:00","therapist":"%s"}\n' "$p" "$DAY" "$h" "$t"
      done
    done
  done | tr "\n" "\0" | xargs -0 -P 4 -I{} curl -s -o /dev/null -X POST "$TOOLS/cancel-booking" ${AUTH[@]+"${AUTH[@]}"} -H 'Content-Type: application/json' -d '{}'
}
trap 'cleanup; rm -rf "$OUT"' EXIT
cleanup

echo "Mission 3 tests -> $N8N_VOICE_URL (diary day $DAY)"

echo "- speech output fails: caller still gets the words, staff get told"
turn "test-m3-$RUN-a" "Are you open on Saturdays?" -H "X-Simulate-Failure: tts"
[[ $CODE == 200 && $CTYPE == application/json* && $(hdr x-degraded) == tts && -n $REPLY ]] \
  && ok "TTS failure returns the reply as text" || bad "TTS failure should return 200 JSON with the reply text and X-Degraded: tts"
grep -q '"reply"' "$OUT/b" && ok "JSON body carries the reply for the page to show" || bad "JSON body should have a reply field: $(head -c 200 "$OUT/b")"
[[ $(hdr x-alerted) == true ]] && ok "staff alerted about the TTS failure" || bad "X-Alerted should be true after a TTS failure"

echo "- agent fails: caller hears a safe apology, staff get told"
turn "test-m3-$RUN-b" "I would like to book an appointment" -H "X-Simulate-Failure: agent"
[[ $CODE == 200 && $CTYPE == audio/* && $ROUTE == fallback ]] && grep -qi 'call you back' <<<"$REPLY" \
  && ok "agent failure speaks the fallback apology" || bad "agent failure should speak the fallback apology (route=fallback)"
[[ $(hdr x-alerted) == true ]] && ok "staff alerted about the agent failure" || bad "X-Alerted should be true after an agent failure"

echo "- real callers can't trigger simulated failures"
turn "m3-$RUN-c" "Are you open on Saturdays?" -H "X-Simulate-Failure: tts"
[[ $CODE == 200 && $CTYPE == audio/* && $ROUTE == agent ]] && ok "simulation header ignored outside test sessions" || bad "non-test session must ignore X-Simulate-Failure"

echo "- a repeated request is replayed, not processed twice"
RID="m3-$RUN-replay"
turn "m3-$RUN-d" "Please book me with Daniel at 11 am on $SPOKEN. My name is TEST Mission Three, phone +1 000 000 0030." -H "X-Request-Id: $RID"
FIRST=$REPLY
turn "m3-$RUN-d" "Please book me with Daniel at 11 am on $SPOKEN. My name is TEST Mission Three, phone +1 000 000 0030." -H "X-Request-Id: $RID"
[[ $CODE == 200 && $ROUTE == replay && "$REPLY" == "$FIRST" ]] && ok "same X-Request-Id returns the first answer (route=replay)" || bad "repeat should be route=replay with the same reply"
R1=$(tool cancel-booking "{\"phone\":\"+10000000030\",\"date\":\"$DAY\"}")
R2=$(tool cancel-booking "{\"phone\":\"+10000000030\",\"date\":\"$DAY\"}")
[[ $(field "$R1" 'd["cancelled"]') == True && $(field "$R2" 'd["cancelled"]') == False ]] \
  && ok "exactly one booking exists after the replay" || bad "expected exactly one booking for the replayed request: $R1 / $R2"

echo "- two callers grab the same slot at the same moment"
for i in 1 2 3 4; do
  tool create-booking "{\"date\":\"$DAY\",\"time\":\"15:00\",\"therapist\":\"Sara\",\"patientName\":\"TEST Race $i\",\"phone\":\"+1000000003$i\"}" > "$OUT/race$i" &
done; wait
WON=$(cat "$OUT"/race* | python3 -I -c 'import sys,json; print(sum(1 for l in sys.stdin.read().replace("}{","}\n{").splitlines() if json.loads(l).get("booked")))')
[[ $WON == 1 ]] && ok "4 simultaneous requests -> exactly 1 booking" || bad "4 simultaneous requests for Sara 15:00 gave $WON bookings: $(cat "$OUT"/race*)"
LOST=$(cat "$OUT"/race* | python3 -I -c 'import sys,json; r=[json.loads(l) for l in sys.stdin.read().replace("}{","}\n{").splitlines()]; l=[x for x in r if not x.get("booked")]; print(all(x.get("alternatives") for x in l) and len(l)==3)')
[[ $LOST == True ]] && ok "the other callers are offered alternatives" || bad "losing callers should get alternatives"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
