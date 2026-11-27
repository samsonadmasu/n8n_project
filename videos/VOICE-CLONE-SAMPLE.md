# Voice clone: what to read

Read this aloud once, at your normal pace, as if you're explaining your work to a client. It takes about two minutes.
It includes the words the videos use (n8n, ElevenLabs, webhook, Gemini, Pushover, Amina), so the clone learns how you say them.

---

Hi, I'm Samson. I build automations with n8n, and in this project I built a voice receptionist for a physiotherapy clinic called Northgate Physio.

The clinic has three therapists, Amina, Daniel and Sara. They were missing about a quarter of their calls, mostly people trying to book. So I built a system that answers the phone, checks the diary, and books or cancels appointments on its own.

It starts with a webhook. A recording comes in, gets checked, and goes to ElevenLabs to turn speech into text. Then an AI agent decides what to say. It runs on OpenAI, and if OpenAI is down, Gemini takes over automatically. Finally, ElevenLabs turns the reply back into a voice.

What I'm proudest of is how it handles problems. If the voice service fails, the caller still gets the answer as text. If two people try to book the last slot at the same moment, only one of them gets it, and the other is offered the nearest free time. And whenever something goes wrong, the staff get a Pushover notification on their phone, with a link to the exact run.

Is it perfect? No. But every part of it is tested, and the tests caught real bugs before any caller did. One time the audio quietly disappeared between two steps. Another time, four bookings landed on the same slot. Both are fixed now.

Thanks for listening. Let's open the workflows and look inside each step.

---

## Recording tips

- Quiet room, no music, fan or echo. A small room with soft furniture works better than a kitchen.
- Phone or laptop mic about a hand's width from your mouth, off to the side a little.
- Speak naturally. Don't read slowly or "announcer style": the clone copies whatever style you use here.
- If you stumble, pause and repeat the sentence. Small mistakes are fine.
- Record 1–2 minutes. More clean audio helps; noisy audio hurts.
