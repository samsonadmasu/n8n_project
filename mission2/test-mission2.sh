#!/usr/bin/env bash
# Mission 2 acceptance tests: the voice loop has a brain.
#
# Talks to the same webhook as Mission 1, but sends typed turns (form field "message")
# so the tests don't depend on speech recognition. Every reply is still spoken audio;
# the webhook also returns:
#   X-Route       agent | urgent
#   X-Reply-Text  the reply, URI-encoded
# Booking state is checked through the Mission 6 availability webhook, so these tests
# prove the agent really changed the diary, not just that it said so.
#
# LLM replies vary. Checks look for meaning (a name, a word like "closed"), and booking
# steps allow up to three turns because the agent may confirm details first.
set -u
cd "$(dirname "$0")"
[ -f ../mission1/.env ] && set -a && . ../mission1/.env && set +a
: "${N8N_VOICE_URL:?Set N8N_VOICE_URL in mission1/.env}"
CHECK="${N8N_VOICE_URL%%/webhook/*}/webhook/northgate-tools/check-availability"
AUTH=(); [ "${DESK_AUTH:-key}" != none ] && AUTH=(-H "X-Desk-Key: ${N8N_DESK_KEY:?}")

read -r DAY SPOKEN < <(python3 -I -c '
import datetime as d
w=d.date.today()+d.timedelta(days=15)
while w.weekday()>4: w+=d.timedelta(days=1)
print(w, w.strftime("%A")+"_"+str(w.day)+"_"+w.strftime("%B"))')
SPOKEN=${SPOKEN//_/ }
RUN=$$
OUT=$(mktemp -d); trap 'rm -rf "$OUT"' EXIT
pass=0; fail=0
ok()  { echo "  PASS  $1"; pass=$((pass+1)); }
bad() { echo "  FAIL  $1"; fail=$((fail+1)); }

# say <session> <message>  -> sets CODE ROUTE REPLY
say() {
  local hdr="$OUT/h"
  CODE=$(curl -s -o "$OUT/a" -D "$hdr" -w '%{http_code}' -X POST "$N8N_VOICE_URL" ${AUTH[@]+"${AUTH[@]}"} \
    -H "X-Session-Id: $1" -F "message=$2")
  ROUTE=$(grep -i '^x-route:' "$hdr" | cut -d' ' -f2- | tr -d '\r')
  REPLY=$(grep -i '^x-reply-text:' "$hdr" | cut -d' ' -f2- | tr -d '\r' | python3 -I -c 'import sys,urllib.parse;print(urllib.parse.unquote(sys.stdin.read().strip()))')
  echo "        you: $2"
  echo "        bot: ${REPLY:-<no reply text>} [$CODE ${ROUTE:-no-route}]"
}
amina_free_at_14() {
  curl -s -X POST "$CHECK" ${AUTH[@]+"${AUTH[@]}"} -H 'Content-Type: application/json' -d "{\"date\":\"$DAY\",\"therapist\":\"Amina\"}" \
    | python3 -I -c 'import json,sys; print("14:00" in [s["time"] for s in json.load(sys.stdin).get("free",[])])'
}

echo "Mission 2 tests -> $N8N_VOICE_URL (diary day $DAY = $SPOKEN)"

echo "- typed turn is answered by the agent"
say "m2-$RUN-a" "Hello, who am I speaking to?"
[[ $CODE == 200 && $ROUTE == agent && -n $REPLY && $(wc -c < "$OUT/a") -gt 2000 ]] \
  && ok "typed message gets a spoken agent reply" || bad "typed message should get audio from the agent route"

echo "- emergency guardrail"
say "m2-$RUN-b" "I have chest pain and I can't breathe properly"
[[ $CODE == 200 && $ROUTE == urgent ]] && grep -qi 'emergency' <<<"$REPLY" \
  && ok "chest pain goes to the fixed safety script, not the agent" || bad "chest pain should route=urgent with the emergency script"

echo "- clinic FAQ"
say "m2-$RUN-c" "Are you open on Sundays?"
[[ $CODE == 200 && $ROUTE == agent ]] && grep -Eqi "closed|not open|don.t open|aren.t open" <<<"$REPLY" \
  && ok "knows the clinic is closed on Sunday" || bad "should say the clinic is closed on Sunday"

echo "- memory across turns"
say "m2-$RUN-d" "Hi, my name is Zebulon Quarrington."
say "m2-$RUN-d" "Sorry, can you remind me what name I gave you?"
grep -qi 'zebulon' <<<"$REPLY" && ok "remembers the caller's name in the same session" || bad "should remember the name Zebulon within a session"
say "m2-$RUN-e" "What name did I give you?"
grep -qi 'zebulon' <<<"$REPLY" && bad "a different session must not know the name" || ok "a new session doesn't know the name"

echo "- availability from the real diary"
[[ $(amina_free_at_14) == True ]] && ok "Amina 14:00 on $DAY is free before the test" || bad "Amina 14:00 on $DAY should be free before the test (left-over booking?)"
S="m2-$RUN-f"
say "$S" "What times does Amina have free on $SPOKEN?"
grep -Eqi "nine|9|two|2 ?p|14" <<<"$REPLY" && ok "offers times from the diary" || bad "should offer some of Amina's free times"

echo "- booking by conversation"
say "$S" "Please book me with Amina at 2 pm that day. My name is TEST Mission Two and my phone number is +1 000 000 0022."
for _ in 1 2 3; do
  [[ $(amina_free_at_14) == False ]] && break
  say "$S" "Yes, that's all correct, please go ahead and book it."
done
[[ $(amina_free_at_14) == False ]] && ok "the slot is really taken in the diary" || bad "Amina 14:00 should be booked after the conversation"

echo "- cancelling by conversation"
say "$S" "Actually, please cancel that appointment."
for _ in 1 2 3; do
  [[ $(amina_free_at_14) == True ]] && break
  say "$S" "Yes, I'm sure, please cancel it. The phone number is +1 000 000 0022."
done
[[ $(amina_free_at_14) == True ]] && ok "the slot is free again after cancelling" || bad "Amina 14:00 should be free after cancelling"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
