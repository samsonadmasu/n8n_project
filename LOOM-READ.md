# Read-aloud script: Northgate Voice Desk

Read the plain text. Lines starting with ▶ are actions, not words to say.
About 5 minutes at a relaxed pace. Pause for a breath at every ▶.

---

## 1 · The problem (about 40 seconds)

▶ Tab: **Northgate Voice Desk** (the brief). Start at the top.

Hi, I'm Samson. This is a project I built to show how I work as an n8n developer.

The client is Northgate Physio, a clinic with three therapists. They take sixty to ninety calls a day, and they miss about a quarter of them at lunchtime and after five. Most of those missed calls are people trying to book.

They asked for a voice receptionist that can answer questions, book and cancel appointments, and hand anything urgent to a human.

▶ Scroll down slowly to the four targets.

I built against four targets: eighty percent of bookings done without staff, replies in under four seconds, zero double bookings, and about fifteen cents per call.

---

## 2 · How it's built (about 70 seconds)

▶ Tab: **Northgate · Voice Loop**. Press **1** to fit the canvas.

This is the main workflow. A caller sends a recording, or types a message, and it arrives here.

▶ Point along the top row from left to right.

First, the request is checked: empty, too large or the wrong format is rejected before anything costs money. Then it checks whether we've already answered this exact request. If a phone retries, the caller gets the same answer instead of a second booking.

▶ Point at Transcribe, Receptionist and Speak.

Then three reusable sub-workflows do the work: Transcribe turns speech into text, Receptionist decides what to say, and Speak turns the answer back into a voice. Each one can fail on its own without taking the whole call down.

▶ Tab: **Northgate · Receptionist**. Press **1** to fit.

This is the brain. The first step is a guardrail. If a caller mentions chest pain or trouble breathing, they get a fixed safety message telling them to call emergency services. The AI never improvises on that.

▶ Point at the agent and the small nodes underneath it.

Everything else goes to an AI agent. It remembers the conversation, and it has four tools: check availability, book, cancel, and clinic facts like opening hours. It runs on OpenAI, with Gemini as an automatic backup if OpenAI fails.

---

## 3 · The voice agent (about 40 seconds)

▶ Tab: **ElevenLabs**, the Northgate Receptionist tools page.

The same booking tools also power a real-time voice agent in ElevenLabs. These two tools call my n8n webhooks.

In testing, a caller asked for Sara next Wednesday morning. The agent offered three real times from the diary, took the name and phone number, read the number back to confirm it, and booked the appointment with a reference number. The booking was in the diary straight away.

The live instance is paused right now because it's on a usage limit, so I'm walking you through the build rather than calling it live.

---

## 4 · Failing well (about 60 seconds)

▶ Tab: **Northgate · Voice Loop** again. Point at the lower branches.

The part most clients only see when something goes wrong is failure handling, so I tested every failure on purpose.

If the voice service fails, the caller still gets the answer as text.

If both AI providers are down, the caller hears a polite apology and is told a member of staff will call back.

And if two people try to book the last slot at exactly the same moment, only one gets it. The others are offered the nearest free times. I tested that with four bookings arriving at once.

▶ Tab: **Northgate · Staff alerts**. Press **1** to fit.

Every one of those failures also sends the team a push notification to their phone, with a link to the exact run that failed. Crashes anywhere in the system end up here too.

---

## 5 · Proof and close (about 45 seconds)

▶ Stay on Staff alerts, or switch to the brief.

Every part of this has an automated acceptance test that runs against the live system: bookings, cancellations, memory, the emergency message, every fallback, and the double-booking race. Those tests caught real bugs while I was building, including one where two callers could both book the same slot.

Everything is in Git: the workflows, the code inside them, the tests, and a guide to run it all.

For this client, the next steps would be a real phone number through ElevenLabs, appointment reminders, and moving it onto their own server.

Thanks for watching.

▶ Stop recording.
