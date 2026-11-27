"""Builds northgate-agent-tools.workflow.json from the Code-node sources in this folder."""
import json, pathlib, uuid
here = pathlib.Path(__file__).parent
BOOKINGS = "wLHF1O85PJ6QXfGK"   # n8n data table: northgate_bookings
# Webhook auth: "none" while learning; switch to "headerAuth" + the "Northgate desk key" credential before real use.
AUTH = "none"
COLS = ["bookingId", "date", "time", "therapist", "patientName", "phone", "status", "source"]

def webhook(name, path, pos):
    return {"name": name, "type": "n8n-nodes-base.webhook", "typeVersion": 2.2, "position": pos,
            "webhookId": str(uuid.uuid5(uuid.NAMESPACE_URL, "northgate/" + path)),
            "parameters": {"httpMethod": "POST", "path": path, "authentication": AUTH,
                           "responseMode": "responseNode", "options": {}}}

def rows_on_date(name, source, pos):
    return {"name": name, "type": "n8n-nodes-base.dataTable", "typeVersion": 1.1, "position": pos,
            "alwaysOutputData": True,
            "parameters": {"resource": "row", "operation": "get",
                           "dataTableId": {"__rl": True, "mode": "id", "value": BOOKINGS},
                           "matchType": "allConditions",
                           "filters": {"conditions": [{"keyName": "date", "condition": "eq",
                                                       "keyValue": "={{ $('%s').first().json.body.date || '' }}" % source}]},
                           "returnAll": True}}

def code(name, file, pos, notes):
    return {"name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos, "notes": notes,
            "parameters": {"jsCode": (here / file).read_text()}}

def respond(name, body_expr, pos, decider):
    return {"name": name, "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1.5, "position": pos,
            "parameters": {"respondWith": "json", "responseBody": body_expr,
                           "options": {"responseCode": "={{ $('%s').item.json.httpStatus }}" % decider}}}

def gate(name, field, pos):
    return {"name": name, "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": pos,
            "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                                          "conditions": [{"id": field, "leftValue": "={{ $json.%s }}" % field, "rightValue": "",
                                                          "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                                          "combinator": "and"}, "options": {}}}

nodes = [
    webhook("Check availability", "northgate-tools/check-availability", [0, 0]),
    rows_on_date("Bookings that day", "Check availability", [220, 0]),
    code("Work out free times", "check-code.js", [440, 0], "Clinic hours and therapists live in CLINIC at the top."),
    respond("Reply with times", "={{ JSON.stringify($json.reply) }}", [660, 0], "Work out free times"),

    webhook("Book appointment", "northgate-tools/create-booking", [0, 320]),
    rows_on_date("Bookings that day (re-check)", "Book appointment", [220, 320]),
    code("Decide booking", "book-code.js", [440, 320], "Re-checks the slot against fresh rows right before the insert."),
    gate("Can book?", "book", [660, 320]),
    {"name": "Save booking", "type": "n8n-nodes-base.dataTable", "typeVersion": 1.1, "position": [880, 220],
     "parameters": {"resource": "row", "operation": "insert",
                    "dataTableId": {"__rl": True, "mode": "id", "value": BOOKINGS},
                    "columns": {"mappingMode": "defineBelow",
                                "value": {c: "={{ $json.row.%s }}" % c for c in COLS},
                                "matchingColumns": [],
                                "schema": [{"id": c, "displayName": c, "required": False, "defaultMatch": False,
                                            "display": True, "type": "string", "canBeUsedToMatch": True} for c in COLS]},
                    "options": {}}},
    rows_on_date("Bookings that day (after save)", "Book appointment", [1100, 220]),
    code("Did we win the slot?", "race-code.js", [1320, 220], "Two callers, one slot: the row saved first keeps it, later ones undo themselves."),
    gate("Won the slot?", "won", [1540, 220]),
    respond("Reply booked", "={{ JSON.stringify($('Decide booking').item.json.reply) }}", [1760, 120], "Decide booking"),
    {"name": "Undo our booking", "type": "n8n-nodes-base.dataTable", "typeVersion": 1.1, "position": [1760, 320],
     "parameters": {"resource": "row", "operation": "update",
                    "dataTableId": {"__rl": True, "mode": "id", "value": BOOKINGS},
                    "matchType": "allConditions",
                    "filters": {"conditions": [{"keyName": "id", "condition": "eq", "keyValue": "={{ $json.undoRowId }}"}]},
                    "columns": {"mappingMode": "defineBelow", "value": {"status": "cancelled"}, "matchingColumns": [],
                                "schema": [{"id": c, "displayName": c, "required": False, "defaultMatch": False,
                                            "display": True, "type": "string", "canBeUsedToMatch": True,
                                            "removed": c != "status"} for c in COLS]},
                    "options": {}}},
    respond("Reply slot just taken", "={{ JSON.stringify($('Did we win the slot?').item.json.reply) }}", [1980, 320], "Decide booking"),
    respond("Reply not booked", "={{ JSON.stringify($json.reply) }}", [880, 420], "Decide booking"),

    webhook("Cancel appointment", "northgate-tools/cancel-booking", [0, 640]),
    rows_on_date("Bookings that day (cancel)", "Cancel appointment", [220, 640]),
    code("Decide cancellation", "cancel-code.js", [440, 640], "Only cancels when the caller's phone matches the booking."),
    gate("Can cancel?", "cancel", [660, 640]),
    {"name": "Mark cancelled", "type": "n8n-nodes-base.dataTable", "typeVersion": 1.1, "position": [880, 540],
     "parameters": {"resource": "row", "operation": "update",
                    "dataTableId": {"__rl": True, "mode": "id", "value": BOOKINGS},
                    "matchType": "allConditions",
                    "filters": {"conditions": [{"keyName": "id", "condition": "eq", "keyValue": "={{ $json.rowId }}"}]},
                    "columns": {"mappingMode": "defineBelow", "value": {"status": "cancelled"}, "matchingColumns": [],
                                "schema": [{"id": c, "displayName": c, "required": False, "defaultMatch": False,
                                            "display": True, "type": "string", "canBeUsedToMatch": True,
                                            "removed": c != "status"} for c in COLS]},
                    "options": {}}},
    respond("Reply cancelled", "={{ JSON.stringify($('Decide cancellation').item.json.reply) }}", [1100, 540], "Decide cancellation"),
    respond("Reply not cancelled", "={{ JSON.stringify($json.reply) }}", [880, 740], "Decide cancellation"),
]
link = lambda *targets: {"main": [[{"node": t, "type": "main", "index": 0}] for t in targets]}
wf = {"name": "Northgate · Agent tools",
      "settings": {"executionOrder": "v1", "timezone": "Africa/Addis_Ababa", "saveDataSuccessExecution": "all",
                   "errorWorkflow": "IirH2iDy25qNBr69"},
      "nodes": nodes,
      "connections": {
          "Check availability": link("Bookings that day"),
          "Bookings that day": link("Work out free times"),
          "Work out free times": link("Reply with times"),
          "Book appointment": link("Bookings that day (re-check)"),
          "Bookings that day (re-check)": link("Decide booking"),
          "Decide booking": link("Can book?"),
          "Can book?": link("Save booking", "Reply not booked"),
          "Save booking": link("Bookings that day (after save)"),
          "Bookings that day (after save)": link("Did we win the slot?"),
          "Did we win the slot?": link("Won the slot?"),
          "Won the slot?": link("Reply booked", "Undo our booking"),
          "Undo our booking": link("Reply slot just taken"),
          "Cancel appointment": link("Bookings that day (cancel)"),
          "Bookings that day (cancel)": link("Decide cancellation"),
          "Decide cancellation": link("Can cancel?"),
          "Can cancel?": link("Mark cancelled", "Reply not cancelled"),
          "Mark cancelled": link("Reply cancelled"),
      }}
(here / "northgate-agent-tools.workflow.json").write_text(json.dumps(wf, indent=2, ensure_ascii=False))
print(json.dumps(wf, ensure_ascii=False, separators=(",", ":")))
