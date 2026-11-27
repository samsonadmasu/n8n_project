#!/usr/bin/env bash
# Acceptance tests for the two n8n webhooks the ElevenLabs Northgate agent calls.
#
# Reads mission1/.env (same key protects every Northgate webhook):
#   N8N_VOICE_URL  used only to find the n8n base URL
#   N8N_DESK_KEY   value of the "Northgate desk key" Header Auth credential
#
# Clinic rules being tested:
#   Mon-Fri 09:00-16:00 starts, Sat 09:00-12:00 starts, Sunday closed
#   Therapists: Amina, Daniel, Sara. Bookable from tomorrow up to 30 days ahead.
# Test bookings use patientName "TEST Caller" so they are easy to delete.
set -u
cd "$(dirname "$0")"
[ -f ../mission1/.env ] && set -a && . ../mission1/.env && set +a
: "${N8N_VOICE_URL:?Set N8N_VOICE_URL in mission1/.env}"
: "${N8N_DESK_KEY:?Set N8N_DESK_KEY in mission1/.env}"
BASE="${N8N_VOICE_URL%%/webhook/*}/webhook/northgate-tools"
CHECK="$BASE/check-availability"
BOOK="$BASE/create-booking"
CANCEL="$BASE/cancel-booking"

# A weekday about two weeks out, a Sunday, and yesterday.
read -r WEEKDAY SUNDAY YESTERDAY < <(python3 -I -c '
import datetime as d
t=d.date.today(); w=t+d.timedelta(days=14)
while w.weekday()>4: w+=d.timedelta(days=1)
s=t+d.timedelta(days=(6-t.weekday())%7 or 7)
print(w, s, t-d.timedelta(days=1))')

pass=0; fail=0
ok()  { echo "  PASS  $1"; pass=$((pass+1)); }
bad() { echo "  FAIL  $1"; fail=$((fail+1)); }
skip() { echo "  SKIP  $1"; }
auth_off() { [ "${DESK_AUTH:-key}" = none ]; }
call() { # call <url> <json> [extra curl args] -> sets CODE and BODY
  local url=$1 data=$2; shift 2
  BODY=$(curl -s -w $'\n%{http_code}' -X POST "$url" -H 'Content-Type: application/json' "$@" -d "$data")
  CODE=${BODY##*$'\n'}; BODY=${BODY%$'\n'*}
}
K=(-H "X-Desk-Key: $N8N_DESK_KEY")
jq_() { python3 -I -c "import json,sys; d=json.loads(sys.argv[1]); print(eval(sys.argv[2]))" "$BODY" "$1" 2>/dev/null; }

# Test phones only. Cancels any booking they hold on the test day, so every run starts and ends clean.
cleanup() {
  # n8n Cloud limits how many runs execute at once, so cancel 4 at a time, not all at once.
  local p h t
  for p in +10000000000 +10000000001 +10000000002; do
    for h in 09 10 11 12 13 14 15 16; do
      for t in Amina Daniel Sara; do
        printf '{"phone":"%s","date":"%s","time":"%s:00","therapist":"%s"}\n' "$p" "$WEEKDAY" "$h" "$t"
      done
    done
  done | tr "\n" "\0" | xargs -0 -P 4 -I{} curl -s -o /dev/null -X POST "$CANCEL" -H 'Content-Type: application/json' ${K[@]+"${K[@]}"} -d '{}'
}
trap cleanup EXIT

echo "Agent tool tests -> $BASE  (weekday $WEEKDAY, sunday $SUNDAY)"
cleanup

if auth_off; then skip "calls without key refused (DESK_AUTH=none)"; else
call "$CHECK" "{\"date\":\"$WEEKDAY\"}"
[[ $CODE == 401 || $CODE == 403 ]] && ok "check without key refused ($CODE)" || bad "check without key should be 401/403, got $CODE"

call "$BOOK" "{\"date\":\"$WEEKDAY\",\"time\":\"10:00\",\"patientName\":\"TEST Caller\",\"phone\":\"+10000000000\"}"
[[ $CODE == 401 || $CODE == 403 ]] && ok "book without key refused ($CODE)" || bad "book without key should be 401/403, got $CODE"

fi

call "$CHECK" '{}' "${K[@]}"
[[ $CODE == 400 ]] && ok "check without date -> 400: $BODY" || bad "check without date should be 400, got $CODE $BODY"

call "$CHECK" "{\"date\":\"$SUNDAY\"}" "${K[@]}"
[[ $CODE == 200 && $(jq_ 'd["open"]') == False ]] && ok "Sunday is closed: $(jq_ 'd["message"]')" || bad "Sunday should be open:false, got $CODE $BODY"

call "$CHECK" "{\"date\":\"$YESTERDAY\"}" "${K[@]}"
[[ $CODE == 200 && $(jq_ 'd["open"]') == False ]] && ok "past date is not bookable: $(jq_ 'd["message"]')" || bad "yesterday should be open:false, got $CODE $BODY"

call "$CHECK" "{\"date\":\"$WEEKDAY\",\"therapist\":\"Amina\"}" "${K[@]}"
[[ $CODE == 200 && $(jq_ '"10:00" in [s["time"] for s in d["free"]]') == True ]] \
  && ok "Amina has 10:00 free on $WEEKDAY before booking" || bad "Amina 10:00 should be free first, got $CODE $BODY"

call "$BOOK" "{\"date\":\"$WEEKDAY\",\"time\":\"10:00\",\"therapist\":\"Amina\"}" "${K[@]}"
[[ $CODE == 400 ]] && ok "booking without name/phone -> 400: $BODY" || bad "booking without name/phone should be 400, got $CODE $BODY"

call "$BOOK" "{\"date\":\"$WEEKDAY\",\"time\":\"10:00\",\"therapist\":\"Amina\",\"patientName\":\"TEST Caller\",\"phone\":\"+10000000000\"}" "${K[@]}"
[[ $CODE == 200 && $(jq_ 'd["booked"]') == True && -n $(jq_ 'd["bookingId"]') ]] \
  && ok "booked Amina 10:00: $(jq_ 'd["message"]')" || bad "booking should succeed, got $CODE $BODY"

call "$CHECK" "{\"date\":\"$WEEKDAY\",\"therapist\":\"Amina\"}" "${K[@]}"
[[ $CODE == 200 && $(jq_ '"10:00" in [s["time"] for s in d["free"]]') == False ]] \
  && ok "Amina 10:00 no longer free after booking" || bad "Amina 10:00 should be taken now, got $CODE $BODY"

call "$BOOK" "{\"date\":\"$WEEKDAY\",\"time\":\"10:00\",\"therapist\":\"Amina\",\"patientName\":\"TEST Caller Two\",\"phone\":\"+10000000001\"}" "${K[@]}"
[[ $CODE == 200 && $(jq_ 'd["booked"]') == False && $(jq_ 'len(d["alternatives"])>0') == True ]] \
  && ok "double booking refused, offers: $(jq_ 'd["alternatives"]')" || bad "second booking of the same slot should be refused with alternatives, got $CODE $BODY"

call "$BOOK" "{\"date\":\"$WEEKDAY\",\"time\":\"10:00\",\"patientName\":\"TEST Caller Three\",\"phone\":\"+10000000002\"}" "${K[@]}"
[[ $CODE == 200 && $(jq_ 'd["booked"]') == True && $(jq_ 'd["therapist"]') != Amina ]] \
  && ok "no therapist named -> another free therapist: $(jq_ 'd["therapist"]')" || bad "booking with no therapist should pick a free one, got $CODE $BODY"

call "$BOOK" "{\"date\":\"$WEEKDAY\",\"time\":\"10:00\",\"patientName\":\"TEST Caller Three\",\"phone\":\"+10000000002\"}" "${K[@]}"
[[ $CODE == 200 && $(jq_ 'd["booked"]') == False ]] && grep -qi 'already' <<<"$(jq_ 'd["message"]')" \
  && ok "same caller can't hold two appointments at one time: $(jq_ 'd["message"]')" || bad "a second booking for the same phone at the same time should be refused, got $CODE $BODY"

call "$BOOK" "{\"date\":\"$SUNDAY\",\"time\":\"10:00\",\"patientName\":\"TEST Caller\",\"phone\":\"+10000000000\"}" "${K[@]}"
[[ $CODE == 200 && $(jq_ 'd["booked"]') == False ]] && ok "Sunday booking refused: $(jq_ 'd["message"]')" || bad "Sunday booking should be refused, got $CODE $BODY"

# Cancelling (Mission 2): by phone + date + time, never someone else's booking.
call "$CANCEL" "{\"date\":\"$WEEKDAY\",\"time\":\"10:00\"}" "${K[@]}"
[[ $CODE == 400 ]] && ok "cancel without phone -> 400: $BODY" || bad "cancel without phone should be 400, got $CODE $BODY"

call "$CANCEL" "{\"phone\":\"+19999999999\",\"date\":\"$WEEKDAY\",\"time\":\"10:00\"}" "${K[@]}"
[[ $CODE == 200 && $(jq_ 'd["cancelled"]') == False ]] && ok "wrong phone cancels nothing: $(jq_ 'd["message"]')" || bad "wrong phone should not cancel, got $CODE $BODY"

call "$CANCEL" "{\"phone\":\"+1 000 000 0000\",\"date\":\"$WEEKDAY\",\"time\":\"10:00\"}" "${K[@]}"
[[ $CODE == 200 && $(jq_ 'd["cancelled"]') == True ]] && ok "cancelled Amina 10:00: $(jq_ 'd["message"]')" || bad "cancel by phone/date/time should succeed, got $CODE $BODY"

call "$CHECK" "{\"date\":\"$WEEKDAY\",\"therapist\":\"Amina\"}" "${K[@]}"
[[ $CODE == 200 && $(jq_ '"10:00" in [s["time"] for s in d["free"]]') == True ]] \
  && ok "Amina 10:00 is free again after cancelling" || bad "Amina 10:00 should be free after cancel, got $CODE $BODY"

call "$CANCEL" "{\"phone\":\"+10000000002\",\"date\":\"$WEEKDAY\"}" "${K[@]}"
[[ $CODE == 200 && $(jq_ 'd["cancelled"]') == True ]] && ok "cancel by phone + date alone when there is one booking" || bad "phone+date with a single booking should cancel it, got $CODE $BODY"

# Speed: an agent waits on these while the caller listens to silence.
t=$(curl -s -o /dev/null -w '%{time_total}' -X POST "$CHECK" -H 'Content-Type: application/json' "${K[@]}" -d "{\"date\":\"$WEEKDAY\"}")
awk "BEGIN{exit !($t < 1.5)}" && ok "check-availability answers in ${t}s (< 1.5 s)" || bad "check-availability took ${t}s, target < 1.5 s"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
