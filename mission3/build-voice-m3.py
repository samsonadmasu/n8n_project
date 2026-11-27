"""Mission 3: make the voice loop fail well.

Starts from Mission 2's workflow (../mission2/northgate-voice.workflow.json, rebuilt first) and adds:
  - retries + timeouts on ElevenLabs, the agent and the booking tools
  - fallbacks: STT fails -> 502 JSON; agent fails -> spoken apology; TTS fails -> reply as text
  - every fallback calls "Northgate · Staff alerts" (Pushover + alerts table)
  - replay: a repeated X-Request-Id gets the earlier answer instead of running again
  - a crash anywhere goes to the same alerts workflow (settings.errorWorkflow)
  - X-Simulate-Failure (tts | agent) for test-* sessions only, so failures can be tested safely

Run: python3 build-voice-m3.py > /dev/null   (prints minified JSON on stdout for uploading)
"""
import json, pathlib, subprocess, sys

here = pathlib.Path(__file__).parent
m2 = here.parent / "mission2"
subprocess.run([sys.executable, "-I", str(m2 / "build-voice.py")], check=True, stdout=subprocess.DEVNULL)
wf = json.loads((m2 / "northgate-voice.workflow.json").read_text())

ALERTS = "IirH2iDy25qNBr69"   # Northgate · Staff alerts
LOG_TABLE = "UCyU48d9L1hJWBQU"
VOICE = "CwhRBWXzGAHq8TQ4Fs17"
v = "$('Validate request').item.json"
nodes = {n["name"]: n for n in wf["nodes"]}
conn = wf["connections"]


def node(name, type_, version, pos, params, **extra):
    n = {"name": name, "type": type_, "typeVersion": version, "position": pos, "parameters": params, **extra}
    nodes[name] = n
    return n


def set_fields(name, pos, fields):
    return node(name, "n8n-nodes-base.set", 3.4, pos, {"assignments": {"assignments": [
        {"id": f"{name}-{k}", "name": k, "type": t, "value": val} for k, t, val in fields]}, "options": {}})


def link(src, *targets, output=None):
    """Connect src's outputs to targets; output=i replaces only that output index."""
    outs = conn.setdefault(src, {"main": []})["main"]
    if output is None:
        conn[src]["main"] = [[{"node": t, "type": "main", "index": 0}] for t in targets]
    else:
        while len(outs) <= output:
            outs.append([])
        outs[output] = [{"node": t, "type": "main", "index": 0} for t in targets]


def alert(prefix, pos, node_name, message_expr):
    """Set the alert fields, then call the staff alerts workflow and wait for it."""
    set_fields(f"{prefix} alert", pos, [
        ("workflow", "string", "Northgate · Voice Loop"),
        ("node", "string", node_name),
        ("message", "string", "=" + message_expr + f" (session {{{{ {v}.sessionId }}}})"),
        ("executionUrl", "string", "=https://YOUR-N8N-INSTANCE.app.n8n.cloud/workflow/{{ $workflow.id }}/executions/{{ $execution.id }}")])
    node(f"Tell staff ({prefix})", "n8n-nodes-base.executeWorkflow", 1.2, [pos[0] + 220, pos[1]], {
        "source": "database", "workflowId": {"__rl": True, "mode": "id", "value": ALERTS},
        "options": {"waitForSubWorkflow": True}}, onError="continueRegularOutput")
    link(f"{prefix} alert", f"Tell staff ({prefix})")
    return f"{prefix} alert", f"Tell staff ({prefix})"


ERR = "{{ ($json.error && ($json.error.message || $json.error)) || 'unknown error' }}"
retry = lambda n, tries, wait: n.update(retryOnFail=True, maxTries=tries, waitBetweenTries=wait)

# 1. Validate: simulation switch (test sessions only)
code = nodes["Validate request"]["parameters"]["jsCode"]
code = code.replace(
    "const base = { requestId, sessionId, startedAt: Date.now() };",
    "// Fault injection for tests. Only sessions named test-* can use it, so callers can't trigger it.\n"
    "const simulate = sessionId.startsWith('test-') ? String(headers['x-simulate-failure'] || '').toLowerCase() : '';\n"
    "const base = { requestId, sessionId, simulate, startedAt: Date.now() };")
assert "simulate" in code
nodes["Validate request"]["parameters"]["jsCode"] = code

# 2. Replay: a request id we already answered gets the same answer back, nothing re-runs.
same_request = {"matchType": "allConditions", "filters": {"conditions": [
    {"keyName": "requestId", "condition": "eq", "keyValue": "={{ $json.requestId }}"},
    {"keyName": "outcome", "condition": "eq", "keyValue": "answered"}]}}
node("New request?", "n8n-nodes-base.dataTable", 1.1, [560, 260], {
    "resource": "row", "operation": "rowNotExists",
    "dataTableId": {"__rl": True, "mode": "id", "value": LOG_TABLE}, **same_request})
node("Seen before?", "n8n-nodes-base.dataTable", 1.1, [560, 60], {
    "resource": "row", "operation": "rowExists",
    "dataTableId": {"__rl": True, "mode": "id", "value": LOG_TABLE}, **same_request})
node("Earlier answer", "n8n-nodes-base.dataTable", 1.1, [780, 60], {
    "resource": "row", "operation": "get", "dataTableId": {"__rl": True, "mode": "id", "value": LOG_TABLE},
    "matchType": "allConditions", "filters": {"conditions": [
        {"keyName": "requestId", "condition": "eq", "keyValue": f"={{{{ {v}.requestId }}}}"},
        {"keyName": "outcome", "condition": "eq", "keyValue": "answered"}]},
    "returnAll": False, "limit": 1})
set_fields("Replay answer", [1000, 60], [("reply", "string", "={{ $json.replyText }}"), ("route", "string", "replay")])
conn["Request OK?"]["main"][0] = [{"node": "New request?", "type": "main", "index": 0},
                                  {"node": "Seen before?", "type": "main", "index": 0}]
link("New request?", "Needs speech-to-text?")
link("Seen before?", "Earlier answer")
link("Earlier answer", "Replay answer")
link("Replay answer", "Reply to speak")
for name, x in (("Needs speech-to-text?", 780), ("STT · ElevenLabs", 1000), ("Use transcript", 1220)):
    nodes[name]["position"][0] = x

# 3. Speech-to-text: retry, then a clear 502 + staff alert
retry(nodes["STT · ElevenLabs"], 3, 1000)
nodes["STT · ElevenLabs"]["onError"] = "continueErrorOutput"
a_set, a_call = alert("STT", [1220, -120], "STT · ElevenLabs", "Speech-to-text failed: " + ERR)
link("STT · ElevenLabs", "Use transcript", output=0)
link("STT · ElevenLabs", a_set, output=1)
node("Reply could not hear", "n8n-nodes-base.respondToWebhook", 1.5, [1660, -120], {
    "respondWith": "json", "options": {"responseCode": 502},
    "responseBody": f"={{{{ JSON.stringify({{ error: \"Sorry, we couldn't process the recording. Please try again, or type your message.\", requestId: {v}.requestId }}) }}}}"})
link(a_call, "Reply could not hear")

# 4. Agent: fallback model already set; add a retry, and a spoken apology + alert if it still fails
agent = nodes["Receptionist agent"]
retry(agent, 2, 500)
agent["onError"] = "continueErrorOutput"
# Simulate "both model providers are down" for test sessions: point both models at a model that doesn't exist.
nodes["OpenAI model"]["parameters"]["model"]["mode"] = "id"
nodes["OpenAI model"]["parameters"]["model"]["value"] = f"={{{{ {v}.simulate === 'agent' ? 'simulated-broken-model' : 'gpt-4.1-mini' }}}}"
nodes["Gemini fallback"]["parameters"]["modelName"] = f"={{{{ {v}.simulate === 'agent' ? 'models/simulated-broken-model' : 'models/gemini-3-flash-preview' }}}}"
a_set, a_call = alert("Agent", [2260, 480], "Receptionist agent", "The receptionist agent failed: " + ERR)
link("Receptionist agent", "Agent reply", output=0)
link("Receptionist agent", a_set, output=1)
set_fields("Fallback apology", [2700, 480], [
    ("reply", "string", "Sorry, I'm having trouble with the booking system right now. A member of staff will call you back shortly."),
    ("route", "string", "fallback"), ("alerted", "boolean", "={{ !$json.error }}")])
link(a_call, "Fallback apology")
link("Fallback apology", "Reply to speak")
nodes["Reply to speak"]["parameters"]["assignments"]["assignments"].append(
    {"id": "Reply to speak-alerted", "name": "alerted", "type": "boolean", "value": "={{ $json.alerted === true }}"})
for t in ("check_availability", "create_booking", "cancel_booking"):
    nodes[t]["parameters"]["options"] = {"timeout": 8000}

# 5. Text-to-speech: retry, then return the words as JSON + alert
tts = nodes["TTS · ElevenLabs"]
retry(tts, 3, 500)
tts["onError"] = "continueErrorOutput"
tts["parameters"]["voice"] = {"__rl": True, "mode": "id",
                              "value": f"={{{{ {v}.simulate === 'tts' ? 'simulated-broken-voice' : '{VOICE}' }}}}"}
a_set, a_call = alert("TTS", [2920, 420], "TTS · ElevenLabs", "Text-to-speech failed, caller got text only: " + ERR)
link("TTS · ElevenLabs", "Reply with audio", output=0)
link("TTS · ElevenLabs", a_set, output=1)
expose = "X-Request-Id, X-Session-Id, X-Route, X-Reply-Text, X-Transcript, X-Degraded, X-Alerted"
node("Reply with text", "n8n-nodes-base.respondToWebhook", 1.5, [3360, 420], {
    "respondWith": "json",
    "responseBody": f"={{{{ JSON.stringify({{ reply: $('Reply to speak').item.json.reply, route: $('Reply to speak').item.json.route, audio: false, requestId: {v}.requestId }}) }}}}",
    "options": {"responseHeaders": {"entries": [
        {"name": "X-Request-Id", "value": f"={{{{ {v}.requestId }}}}"},
        {"name": "X-Session-Id", "value": f"={{{{ {v}.sessionId }}}}"},
        {"name": "X-Route", "value": "={{ $('Reply to speak').item.json.route }}"},
        {"name": "X-Reply-Text", "value": "={{ encodeURIComponent($('Reply to speak').item.json.reply) }}"},
        {"name": "X-Degraded", "value": "tts"},
        {"name": "X-Alerted", "value": "={{ $json.error ? 'false' : 'true' }}"},
        {"name": "Access-Control-Expose-Headers", "value": expose}]}}})
link(a_call, "Reply with text")
entries = nodes["Reply with audio"]["parameters"]["options"]["responseHeaders"]["entries"]
entries[:] = [e for e in entries if e["name"] != "Access-Control-Expose-Headers"] + [
    {"name": "X-Alerted", "value": "={{ $('Reply to speak').item.json.alerted ? 'true' : 'false' }}"},
    {"name": "Access-Control-Expose-Headers", "value": expose}]

# 6. Logging: keep the reply text (for replays) and log the text-only path too
LOG_COLS = ["requestId", "sessionId", "route", "outcome", "httpStatus", "audioBytes", "mimeType",
            "transcriptChars", "replyChars", "totalMs", "error", "replyText"]
ans = nodes["Log row · answered"]["parameters"]["assignments"]["assignments"]
ans.append({"id": "Log row · answered-replyText", "name": "replyText", "type": "string",
            "value": "={{ $('Reply to speak').item.json.reply }}"})
text_row = json.loads(json.dumps(nodes["Log row · answered"]))
text_row.update(name="Log row · text only", position=[3580, 420])
for a in text_row["parameters"]["assignments"]["assignments"]:
    a["id"] = a["id"].replace("answered", "text only")
    if a["name"] == "outcome":
        a["value"] = "answered-text-only"
    if a["name"] == "error":
        a["value"] = "TTS failed"
nodes[text_row["name"]] = text_row
link("Reply with text", "Log row · text only")
link("Log row · text only", "Log request")
log = nodes["Log request"]["parameters"]["columns"]
log["schema"].append({"id": "replyText", "displayName": "replyText", "required": False, "defaultMatch": False,
                      "display": True, "type": "string", "canBeUsedToMatch": True})
nodes["Log request"]["position"] = [3800, 340]

wf["nodes"] = list(nodes.values())
wf["settings"]["errorWorkflow"] = ALERTS
# A replay skips "Check for emergencies"; anything that reads it must cope with it not having run.
wf = json.loads(json.dumps(wf).replace(
    "$('Check for emergencies').item.json.callerText",
    "($('Check for emergencies').isExecuted ? $('Check for emergencies').item.json.callerText : '')"))
(here / "northgate-voice-m3.workflow.json").write_text(json.dumps(wf, indent=2, ensure_ascii=False))
print(json.dumps(wf, ensure_ascii=False, separators=(",", ":")))
