"""Builds northgate-voice.workflow.json (Mission 2 voice loop) from the files in this folder.

Run: python3 build-voice.py > /dev/null   (prints the minified JSON to stdout for uploading)
"""
import json, pathlib

here = pathlib.Path(__file__).parent
read = lambda f: (here / f).read_text()

AUTH = "none"  # switch to "headerAuth" + the "Northgate desk key" credential before real use
LOG_TABLE = "UCyU48d9L1hJWBQU"  # northgate_voice_log
TOOLS = "https://YOUR-N8N-INSTANCE.app.n8n.cloud/webhook/northgate-tools"
ELEVEN = {"elevenLabsApi": {"id": "SvCckO55wBkLq7Iz", "name": "ElevenLabs account"}}
OPENAI = {"openAiApi": {"id": "tmHPFKBeRyUYHskh", "name": "OpenAI account"}}
GEMINI = {"googlePalmApi": {"id": "Gq9VWEHrCD8soKLO", "name": "Google Gemini(PaLM) Api account"}}
MODEL = "gpt-4.1-mini"  # fast, non-reasoning: good for spoken turns. Gemini free tier hit 429s on tool calls.
LOG_COLS = [("requestId", "string"), ("sessionId", "string"), ("route", "string"), ("outcome", "string"),
            ("httpStatus", "number"), ("audioBytes", "number"), ("mimeType", "string"),
            ("transcriptChars", "number"), ("replyChars", "number"), ("totalMs", "number"), ("error", "string")]


def node(name, type_, version, pos, params, **extra):
    return {"name": name, "type": type_, "typeVersion": version, "position": pos, "parameters": params, **extra}


def if_true(name, expr, pos):
    return node(name, "n8n-nodes-base.if", 2.2, pos, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                       "conditions": [{"id": name, "leftValue": expr, "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                       "combinator": "and"}, "options": {}})


def set_fields(name, pos, fields, include_other=False):
    params = {"assignments": {"assignments": [
        {"id": f"{name}-{k}", "name": k, "type": t, "value": v} for k, t, v in fields]}, "options": {}}
    if include_other:
        params["includeOtherFields"] = True
    return node(name, "n8n-nodes-base.set", 3.4, pos, params)


def http_tool(name, pos, description, path, body_expr):
    return node(name, "n8n-nodes-base.httpRequestTool", 4.2, pos, {
        "toolDescription": description, "method": "POST", "url": f"{TOOLS}/{path}",
        "sendBody": True, "contentType": "json", "specifyBody": "json", "jsonBody": body_expr, "options": {}})


def log_row(name, pos, fields):
    return set_fields(name, pos, fields)


v = "$('Validate request').item.json"
nodes = [
    node("Voice request", "n8n-nodes-base.webhook", 2.2, [0, 300], {
        "httpMethod": "POST", "path": "northgate-voice", "authentication": AUTH,
        "responseMode": "responseNode", "options": {"allowedOrigins": "*"}},
        webhookId="333f6c8b-dba0-43d1-9dab-dd47fcc3b03d"),
    node("Validate request", "n8n-nodes-base.code", 2, [220, 300], {"jsCode": read("validate-code.js")},
         notes="Recording or typed message. Rejects bad input before anything costs money."),
    if_true("Request OK?", "={{ $json.ok }}", [440, 300]),
    if_true("Needs speech-to-text?", "={{ $json.needsStt }}", [660, 200]),
    node("STT · ElevenLabs", "@elevenlabs/n8n-nodes-elevenlabs.elevenLabs", 1, [880, 100], {
        "resource": "speech", "operation": "speechToText", "file": "audio", "additionalOptions": {}, "requestOptions": {}},
        credentials=ELEVEN),
    set_fields("Use transcript", [1100, 100], [("callerText", "string", "={{ $json.text }}")]),
    node("Check for emergencies", "n8n-nodes-base.code", 2, [1320, 200], {"jsCode": read("emergency-code.js")},
         notes="Fixed safety script for emergencies. The LLM never sees these."),
    if_true("Emergency?", "={{ $json.urgent }}", [1540, 200]),
    set_fields("Safety script", [1760, 60], [
        ("reply", "string", "This sounds like it could be an emergency. Please hang up now and call your local emergency number. If you can't, ask someone near you to call for you."),
        ("route", "string", "urgent")]),
    set_fields("Receptionist prompt", [1760, 300], [
        ("systemPrompt", "string", "=" + read("system-prompt.txt")),
        ("callerText", "string", "={{ $json.callerText }}")]),
    node("Receptionist agent", "@n8n/n8n-nodes-langchain.agent", 3.1, [1980, 300], {
        "promptType": "define", "text": "={{ $json.callerText }}",
        "needsFallback": True,  # OpenAI first; Gemini answers if OpenAI errors (expired key, outage)
        "options": {"systemMessage": "={{ $json.systemPrompt }}"}}),
    node("Gemini fallback", "@n8n/n8n-nodes-langchain.lmChatGoogleGemini", 1.2, [1700, 560], {"options": {}}, credentials=GEMINI),
    node("OpenAI model", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, [1820, 560], {
        "model": {"__rl": True, "mode": "list", "value": MODEL}, "options": {"temperature": 0.3}}, credentials=OPENAI),
    node("Conversation memory", "@n8n/n8n-nodes-langchain.memoryBufferWindow", 1.3, [1940, 560], {
        "sessionIdType": "customKey", "sessionKey": f"={{{{ {v}.sessionId }}}}", "contextWindowLength": 10}),
    http_tool("check_availability", [2060, 560],
              "Get the free appointment start times at Northgate Physio for one date. Call before offering any times.",
              "check-availability",
              "={{ JSON.stringify({ date: $fromAI('date', 'The date in YYYY-MM-DD format', 'string'), "
              "therapist: $fromAI('therapist', 'Amina, Daniel or Sara. Empty string when the caller has no preference', 'string', '') }) }}"),
    http_tool("create_booking", [2180, 560],
              "Book an appointment. Needs the date, a free time, the caller's full name and phone number.",
              "create-booking",
              "={{ JSON.stringify({ date: $fromAI('date', 'The date in YYYY-MM-DD format', 'string'), "
              "time: $fromAI('time', 'Start time in 24-hour HH:MM', 'string'), "
              "therapist: $fromAI('therapist', 'Amina, Daniel or Sara. Empty string when the caller has no preference', 'string', ''), "
              "patientName: $fromAI('patientName', 'The caller full name', 'string'), "
              "phone: $fromAI('phone', 'The caller phone number, digits with optional leading +', 'string'), "
              "source: 'voice-loop' }) }}"),
    http_tool("cancel_booking", [2300, 560],
              "Cancel the caller's appointment. Needs their phone number and the date; add the time if they have more than one booking that day.",
              "cancel-booking",
              "={{ JSON.stringify({ phone: $fromAI('phone', 'The caller phone number, digits with optional leading +', 'string'), "
              "date: $fromAI('date', 'The date of the appointment in YYYY-MM-DD format', 'string'), "
              "time: $fromAI('time', 'Start time in 24-hour HH:MM, or empty string if not known', 'string', '') }) }}"),
    node("clinic_faq", "@n8n/n8n-nodes-langchain.toolCode", 1.3, [2420, 560], {
        "description": "Facts about Northgate Physio: opening hours, therapists, appointment length, booking window, what to bring, cancellation notice, prices.",
        "language": "javaScript", "jsCode": read("faq-tool.js")}),
    set_fields("Agent reply", [2260, 300], [("reply", "string", "={{ $json.output }}"), ("route", "string", "agent")]),
    set_fields("Reply to speak", [2480, 200], [("reply", "string", "={{ $json.reply }}"), ("route", "string", "={{ $json.route }}")]),
    node("TTS · ElevenLabs", "@elevenlabs/n8n-nodes-elevenlabs.elevenLabs", 1, [2700, 200], {
        "resource": "speech", "text": "={{ $json.reply }}",
        "voice": {"__rl": True, "mode": "list", "value": "CwhRBWXzGAHq8TQ4Fs17", "cachedResultName": "Roger - Laid-Back, Casual, Resonant"},
        "additionalOptions": {}, "requestOptions": {}}, credentials=ELEVEN),
    node("Reply with audio", "n8n-nodes-base.respondToWebhook", 1.5, [2920, 200], {
        "respondWith": "binary", "responseDataSource": "set",
        "options": {"responseHeaders": {"entries": [
            {"name": "X-Request-Id", "value": f"={{{{ {v}.requestId }}}}"},
            {"name": "X-Session-Id", "value": f"={{{{ {v}.sessionId }}}}"},
            {"name": "X-Route", "value": "={{ $('Reply to speak').item.json.route }}"},
            {"name": "X-Reply-Text", "value": "={{ encodeURIComponent($('Reply to speak').item.json.reply) }}"},
            {"name": "X-Transcript", "value": "={{ encodeURIComponent($('Check for emergencies').item.json.callerText) }}"},
            {"name": "Access-Control-Expose-Headers", "value": "X-Request-Id, X-Session-Id, X-Route, X-Reply-Text, X-Transcript"}]}}}),
    node("Reply with error", "n8n-nodes-base.respondToWebhook", 1.5, [660, 480], {
        "respondWith": "json",
        "responseBody": "={{ JSON.stringify({ error: $json.error, requestId: $json.requestId }) }}",
        "options": {"responseCode": "={{ $json.status }}"}}),
    log_row("Log row · answered", [3140, 200], [
        ("requestId", "string", f"={{{{ {v}.requestId }}}}"),
        ("sessionId", "string", f"={{{{ {v}.sessionId }}}}"),
        ("route", "string", "={{ $('Reply to speak').item.json.route }}"),
        ("outcome", "string", "answered"),
        ("httpStatus", "number", 200),
        ("audioBytes", "number", f"={{{{ {v}.bytes }}}}"),
        ("mimeType", "string", f"={{{{ {v}.mimeType }}}}"),
        ("transcriptChars", "number", "={{ $('Check for emergencies').item.json.callerText.length }}"),
        ("replyChars", "number", "={{ $('Reply to speak').item.json.reply.length }}"),
        ("totalMs", "number", f"={{{{ Date.now() - {v}.startedAt }}}}"),
        ("error", "string", "")]),
    log_row("Log row · rejected", [880, 480], [
        ("requestId", "string", f"={{{{ {v}.requestId }}}}"),
        ("sessionId", "string", f"={{{{ {v}.sessionId }}}}"),
        ("route", "string", "rejected"),
        ("outcome", "string", "rejected"),
        ("httpStatus", "number", f"={{{{ {v}.status }}}}"),
        ("audioBytes", "number", f"={{{{ {v}.bytes ?? 0 }}}}"),
        ("mimeType", "string", f"={{{{ {v}.mimeType ?? '' }}}}"),
        ("transcriptChars", "number", 0),
        ("replyChars", "number", 0),
        ("totalMs", "number", f"={{{{ Date.now() - {v}.startedAt }}}}"),
        ("error", "string", f"={{{{ {v}.error }}}}")]),
    node("Log request", "n8n-nodes-base.dataTable", 1.1, [3360, 340], {
        "resource": "row", "operation": "insert",
        "dataTableId": {"__rl": True, "mode": "id", "value": LOG_TABLE},
        "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [],
                    "schema": [{"id": c, "displayName": c, "required": False, "defaultMatch": False, "display": True,
                                "type": t, "canBeUsedToMatch": True} for c, t in LOG_COLS]},
        "options": {}}),
]

main = lambda *targets: {"main": [[{"node": t, "type": "main", "index": 0}] if t else [] for t in targets]}
ai = lambda kind, target: {kind: [[{"node": target, "type": kind, "index": 0}]]}
connections = {
    "Voice request": main("Validate request"),
    "Validate request": main("Request OK?"),
    "Request OK?": main("Needs speech-to-text?", "Reply with error"),
    "Needs speech-to-text?": main("STT · ElevenLabs", "Check for emergencies"),
    "STT · ElevenLabs": main("Use transcript"),
    "Use transcript": main("Check for emergencies"),
    "Check for emergencies": main("Emergency?"),
    "Emergency?": main("Safety script", "Receptionist prompt"),
    "Safety script": main("Reply to speak"),
    "Receptionist prompt": main("Receptionist agent"),
    "Receptionist agent": main("Agent reply"),
    "Agent reply": main("Reply to speak"),
    "Reply to speak": main("TTS · ElevenLabs"),
    "TTS · ElevenLabs": main("Reply with audio"),
    "Reply with audio": main("Log row · answered"),
    "Reply with error": main("Log row · rejected"),
    "Log row · answered": main("Log request"),
    "Log row · rejected": main("Log request"),
    "OpenAI model": ai("ai_languageModel", "Receptionist agent"),
    "Gemini fallback": {"ai_languageModel": [[{"node": "Receptionist agent", "type": "ai_languageModel", "index": 1}]]},
    "Conversation memory": ai("ai_memory", "Receptionist agent"),
    "check_availability": ai("ai_tool", "Receptionist agent"),
    "create_booking": ai("ai_tool", "Receptionist agent"),
    "cancel_booking": ai("ai_tool", "Receptionist agent"),
    "clinic_faq": ai("ai_tool", "Receptionist agent"),
}
wf = {"name": "Northgate · Voice Loop", "settings": {"executionOrder": "v1", "binaryMode": "separate",
                                                     "timezone": "Africa/Addis_Ababa"},
      "nodes": nodes, "connections": connections}
(here / "northgate-voice.workflow.json").write_text(json.dumps(wf, indent=2, ensure_ascii=False))
print(json.dumps(wf, ensure_ascii=False, separators=(",", ":")))
