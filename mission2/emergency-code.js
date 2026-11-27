// Guardrail: runs BEFORE the AI agent. Anything that sounds like an emergency gets a fixed,
// reviewed safety script. The LLM never improvises on these.
const URGENT = [
  /chest pain/i, /heart attack/i, /stroke/i,
  /can'?t breathe|cannot breathe|trouble breathing|difficulty breathing|short(ness)? of breath|struggling to breathe/i,
  /unconscious|passed out|fainted|not responding/i,
  /heavy bleeding|bleeding (a lot|heavily|badly)|won'?t stop bleeding/i,
  /hit (my|his|her|their) head|head injury|fell .*head/i,
  /suicid|kill myself|overdose/i,
];
const callerText = String($input.first().json.callerText || '').trim();
const matched = URGENT.find(r => r.test(callerText));
return [{ json: { callerText, urgent: Boolean(matched), matched: matched ? String(matched) : '' } }];
