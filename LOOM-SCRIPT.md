# Loom walkthrough: Northgate Voice Desk (about 5 minutes)

**Audience:** a client or hiring manager who wants to know whether you can build reliable n8n automations.
**Goal:** show one real problem, one working system, and proof that it fails safely. Don't explain every node.

## Before you press record

1. Check n8n is running workflows again (it stopped on 17 Nov, probably the Starter plan's monthly limit):
   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' -X POST https://YOUR-N8N-INSTANCE.app.n8n.cloud/webhook/northgate-tools/check-availability -H 'Content-Type: application/json' -d '{"date":"2026-12-01"}'
   ```
   `200` means you can demo live. Anything else: use the **"If n8n is down"** notes in scenes 3 and 4.
2. Open these tabs, in this order, so you only ever click one tab to the right:
   1. `northgate-voice-desk.html` (the brief), opened from the project folder
   2. n8n → **Northgate · Voice Loop** (fit to screen: press `1`, or click "Zoom to fit")
   3. n8n → **Northgate · Receptionist**
   4. ElevenLabs → Agents → **Northgate Receptionist** → Preview
   5. n8n → **Data tables → northgate_bookings**
   6. n8n → **Northgate · Staff alerts**, plus your phone with Pushover open
   7. A terminal in the project folder
3. Close Slack, email and anything with notifications. Hide bookmarks. Zoom browser to 110%.
4. Don't show `.env`, credentials pages or API keys at any point.

## The script

### 0:00 – 0:30 · The problem (tab 1: the brief)
> "This is Northgate Physio, a three-therapist clinic. They miss about a quarter of their calls at lunch and after five, and most of those calls are bookings. They asked for a voice receptionist that books, moves and cancels appointments, answers basic questions, and never guesses about anything urgent."

Scroll to the four targets (80% handled, under 4 s, zero double bookings, $0.15 per call). Point at them:
> "These are the numbers I built against."

### 0:30 – 1:30 · How it's built (tabs 2 and 3)
On **Voice Loop**, move left to right along the canvas:
> "A request comes in, as a recording or typed. It's validated before anything costs money. Then it goes to three reusable sub-workflows: Transcribe, Receptionist, Speak. Each step can fail on its own without taking the call down."

Switch to **Receptionist**:
> "This is the brain. First a guardrail: anything that sounds like an emergency gets a fixed safety script, so the AI never improvises on chest pain. Then the agent, with memory per conversation and four tools: check availability, book, cancel, and clinic facts. OpenAI first, Gemini as automatic fallback."

### 1:30 – 2:45 · Live demo (tab 4: ElevenLabs preview)
Click the call button and say:
1. *"Hi, is Sara free next Wednesday morning?"* → it offers real times from the diary.
2. *"Ten a.m. please. My name is Test Demo, my number is plus one, five five five, zero one zero zero."* → it reads the number back.
3. *"Yes."* → it confirms with a reference number.

Switch to **tab 5 (northgate_bookings)** and refresh:
> "And there's the booking in the diary. Same data whichever channel the caller uses."

**If n8n is down:** show the terminal recording of this conversation from the Mission 2 tests instead (see scene 4) and say *"The live instance is paused on its plan limit, so here's the same conversation from the automated test run."*

### 2:45 – 3:45 · Failing well (tab 6 and your phone)
> "The part clients don't see until it goes wrong: failure handling."

Say each point while showing the matching branch on **Voice Loop** or **Speak**:
- *"If the voice service fails, the caller still gets the words as text."*
- *"If both AI providers are down, the caller hears a safe apology and a promise of a call back."*
- *"Two people grabbing the last slot at the same time: exactly one gets it, the other is offered alternatives. I tested that with four requests at once."*

Open **Staff alerts**, then hold your phone up to the camera:
> "Every one of those sends the team a push notification with a link to the exact execution."

### 3:45 – 4:30 · Proof it works (tab 7: terminal)
Run one suite:
```bash
./mission3/test-mission3.sh
```
While it runs:
> "Every mission has an acceptance test that runs against the live system: bookings, cancellations, memory, the emergency script, every fallback. These are the checks I'd hand over with the project."

**If n8n is down:** don't run it. Open `mission3/test-mission3.sh` and scroll through the test names instead.

### 4:30 – 5:00 · Close (tab 1 or GitHub)
> "Everything is in Git: the workflows, the code inside them, the tests, and a README to run it. Next steps for this client would be phone numbers through ElevenLabs, appointment reminders, and moving it to their own server. Thanks for watching."

## Delivery notes
- Speak to one person. Talk about outcomes ("the caller still gets the words") more than nodes ("the error output of the TTS node").
- If something misbehaves live, say so and keep going. Recovering calmly is part of the demo.
- One take is fine. Use Loom's trim to cut a slow start.
- Before sharing, set the Loom link to "anyone with the link". Don't make it searchable while the webhooks have no key (see README).
