// Mission 4: split the Mission 3 voice loop into sub-workflows.
//
//   Northgate · Transcribe    recording in  -> { ok, text }            (alerts staff on failure)
//   Northgate · Receptionist  caller text   -> { reply, route, alerted } (guardrail, agent, tools, memory)
//   Northgate · Speak         reply text    -> audio, or { ok:false }  (alerts staff on failure)
//   Northgate · Voice Loop    the webhook: validate, replay, call the three above, respond, log
//
// Pure function, no imports: runs in Node (build-m4.js writes the files for git) and pasted into the
// n8n page (to deploy against the live Mission 3 workflow). canonical() gives both sides the same
// fingerprint, so we can prove the deployed workflows match the committed ones.

function split(m3, ids) {
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const byName = Object.fromEntries(m3.nodes.map((n) => [n.name, n]));
  const take = (name, extra = {}) => {
    if (!byName[name]) throw new Error(`Mission 3 workflow has no node "${name}"`);
    const n = clone(byName[name]);
    delete n.id;
    return Object.assign(n, extra);
  };
  const to = (...targets) => ({
    main: targets.map((t) => (t ? [].concat(t).map((node) => ({ node, type: 'main', index: 0 })) : [])),
  });
  const setNode = (name, position, fields, options = {}) => ({
    name, type: 'n8n-nodes-base.set', typeVersion: 3.4, position,
    parameters: { assignments: { assignments: fields.map(([k, t, v]) => ({ id: `${name}-${k}`, name: k, type: t, value: v })) }, options },
  });
  const ifTrue = (name, position, expr) => ({
    name, type: 'n8n-nodes-base.if', typeVersion: 2.2, position,
    parameters: { conditions: { options: { caseSensitive: true, leftValue: '', typeValidation: 'loose', version: 2 },
      conditions: [{ id: name, leftValue: expr, rightValue: '', operator: { type: 'boolean', operation: 'true', singleValue: true } }],
      combinator: 'and' }, options: {} },
  });
  const trigger = (name, inputs) => ({
    name, type: 'n8n-nodes-base.executeWorkflowTrigger', typeVersion: 1.1, position: [0, 300],
    parameters: inputs
      ? { inputSource: 'workflowInputs', workflowInputs: { values: inputs.map(([n, t]) => ({ name: n, type: t })) } }
      : { inputSource: 'passthrough' },
  });
  const call = (name, position, workflowId, inputs) => ({
    name, type: 'n8n-nodes-base.executeWorkflow', typeVersion: 1.2, position,
    parameters: Object.assign(
      { source: 'database', workflowId: { __rl: true, mode: 'id', value: workflowId }, options: { waitForSubWorkflow: true } },
      inputs ? { workflowInputs: {
        mappingMode: 'defineBelow', value: Object.fromEntries(inputs.map(([k, , v]) => [k, v])), matchingColumns: [],
        schema: inputs.map(([k, t]) => ({ id: k, displayName: k, required: false, defaultMatch: false, display: true, canBeUsedToMatch: true, type: t })),
      } } : {}),
  });
  // Every flow here handles one item, so .first() is safe and survives sub-workflow boundaries
  // (paired-item links don't cross them).
  const finish = (wf) => JSON.parse(JSON.stringify(wf).split('.item.json').join('.first().json'));
  const rename = (obj, from, to2) => JSON.parse(JSON.stringify(obj).split(from).join(to2));
  const settings = { executionOrder: 'v1', timezone: 'Africa/Addis_Ababa', errorWorkflow: ids.alerts };
  const V = "$('Validate request')";

  // ---- Transcribe -------------------------------------------------------------------------
  const transcribe = finish(rename({
    name: 'Northgate · Transcribe', settings,
    nodes: [
      trigger('Recording in', null),
      take('STT · ElevenLabs', { position: [220, 300] }),
      setNode('Transcript', [440, 200], [['ok', 'boolean', true], ['text', 'string', '={{ $json.text }}']]),
      Object.assign(take('STT alert', { position: [440, 420] }), {}),
      take('Tell staff (STT)', { position: [660, 420] }),
      setNode('Could not transcribe', [880, 420], [
        ['ok', 'boolean', false], ['status', 'number', 502], ['alerted', 'boolean', '={{ !$json.error }}'],
        ['error', 'string', "Sorry, we couldn't process the recording. Please try again, or type your message."]]),
    ],
    connections: {
      'Recording in': to('STT · ElevenLabs'),
      'STT · ElevenLabs': to('Transcript', 'STT alert'),
      'STT alert': to('Tell staff (STT)'),
      'Tell staff (STT)': to('Could not transcribe'),
    },
    // Binary audio can't be pinned, so Transcribe is exercised through the main webhook tests instead.
    pinData: {},
  }, V, "$('Recording in')").valueOf());
  transcribe.nodes.find((n) => n.name === 'STT alert').parameters.assignments.assignments
    .find((a) => a.name === 'workflow').value = 'Northgate · Transcribe';

  // ---- Receptionist -----------------------------------------------------------------------
  const brain = ['Check for emergencies', 'Emergency?', 'Safety script', 'Receptionist prompt', 'Receptionist agent',
    'OpenAI model', 'Gemini fallback', 'Conversation memory', 'check_availability', 'create_booking', 'cancel_booking',
    'clinic_faq', 'Agent reply', 'Agent alert', 'Tell staff (Agent)', 'Fallback apology'];
  const receptionist = finish(rename({
    name: 'Northgate · Receptionist', settings,
    nodes: [
      trigger('Caller said', [['callerText', 'string'], ['sessionId', 'string'], ['requestId', 'string'], ['simulate', 'string']]),
      ...brain.map((n) => take(n)),
      setNode('Result', [3000, 300], [
        ['reply', 'string', '={{ $json.reply }}'], ['route', 'string', '={{ $json.route }}'],
        ['alerted', 'boolean', '={{ $json.alerted === true }}'],
        ['callerText', 'string', `={{ $('Caller said').item.json.callerText }}`]]),
    ],
    connections: Object.assign(
      { 'Caller said': to('Check for emergencies') },
      Object.fromEntries(Object.entries(clone(m3.connections)).filter(([k]) => brain.includes(k))),
      { 'Safety script': to('Result'), 'Agent reply': to('Result'), 'Fallback apology': to('Result') }),
    pinData: { 'Caller said': [{ json: { callerText: 'Are you open on Saturdays?', sessionId: 'pinned-demo', requestId: 'pinned-demo', simulate: '' } }] },
  }, V, "$('Caller said')"));
  receptionist.nodes.find((n) => n.name === 'Agent alert').parameters.assignments.assignments
    .find((a) => a.name === 'workflow').value = 'Northgate · Receptionist';
  receptionist.nodes.find((n) => n.name === 'Check for emergencies').position = [220, 300];

  // ---- Speak ------------------------------------------------------------------------------
  const speak = finish(rename({
    name: 'Northgate · Speak', settings,
    nodes: [
      trigger('Text in', [['reply', 'string'], ['sessionId', 'string'], ['simulate', 'string']]),
      take('TTS · ElevenLabs', { position: [220, 300] }),
      // Set 3.4 only keeps binary (the audio) with includeOtherFields on and stripBinary off.
      Object.assign(setNode('Audio', [440, 200], [['ok', 'boolean', true], ['alerted', 'boolean', false]], { stripBinary: false }),
        { parameters: { includeOtherFields: true, assignments: { assignments: [
          { id: 'Audio-ok', name: 'ok', type: 'boolean', value: true },
          { id: 'Audio-alerted', name: 'alerted', type: 'boolean', value: false }] }, options: { stripBinary: false } } }),
      take('TTS alert', { position: [440, 420] }),
      take('Tell staff (TTS)', { position: [660, 420] }),
      setNode('No audio', [880, 420], [['ok', 'boolean', false], ['alerted', 'boolean', '={{ !$json.error }}']]),
    ],
    connections: {
      'Text in': to('TTS · ElevenLabs'),
      'TTS · ElevenLabs': to('Audio', 'TTS alert'),
      'TTS alert': to('Tell staff (TTS)'),
      'Tell staff (TTS)': to('No audio'),
    },
    pinData: { 'Text in': [{ json: { reply: 'Hello, this is Northgate Physio. How can I help you today?', sessionId: 'pinned-demo', simulate: '' } }] },
  }, V, "$('Text in')"));
  speak.nodes.find((n) => n.name === 'TTS alert').parameters.assignments.assignments
    .find((a) => a.name === 'workflow').value = 'Northgate · Speak';

  // ---- Voice Loop (orchestrator) ----------------------------------------------------------
  const replyToSpeak = take('Reply to speak', { position: [1540, 300] });
  replyToSpeak.parameters.assignments.assignments.push(
    { id: 'Reply to speak-callerText', name: 'callerText', type: 'string', value: "={{ $json.callerText ?? '' }}" });
  const audio = take('Reply with audio', { position: [2200, 200] });
  const transcriptHeader = audio.parameters.options.responseHeaders.entries.find((e) => e.name === 'X-Transcript');
  transcriptHeader.value = "={{ encodeURIComponent($('Reply to speak').item.json.callerText) }}";
  const text = take('Reply with text', { position: [2200, 400] });
  text.parameters.options.responseHeaders.entries.find((e) => e.name === 'X-Alerted').value = "={{ $json.alerted ? 'true' : 'false' }}";
  const problem = take('Reply with error', { position: [1320, 600] });
  problem.parameters.responseBody = `={{ JSON.stringify({ error: $json.error, requestId: ${V}.item.json.requestId }) }}`;
  problem.parameters.options.responseCode = '={{ $json.status || 502 }}';
  const ran = (n) => `$('${n}').isExecuted`;
  const said = `(${ran('Reply to speak')} ? $('Reply to speak').item.json`;
  const logRow = setNode('Log row', [2420, 400], [
    ['requestId', 'string', `={{ ${V}.item.json.requestId }}`],
    ['sessionId', 'string', `={{ ${V}.item.json.sessionId }}`],
    ['route', 'string', `={{ ${said}.route : 'rejected') }}`],
    ['outcome', 'string', `={{ ${ran('Reply with audio')} ? 'answered' : ${ran('Reply with text')} ? 'answered-text-only' : 'rejected' }}`],
    ['httpStatus', 'number', `={{ ${ran('Reply with error')} ? (${V}.item.json.status || 502) : 200 }}`],
    ['audioBytes', 'number', `={{ ${V}.item.json.bytes ?? 0 }}`],
    ['mimeType', 'string', `={{ ${V}.item.json.mimeType ?? '' }}`],
    ['transcriptChars', 'number', `={{ ${said}.callerText : '').length }}`],
    ['replyChars', 'number', `={{ ${said}.reply : '').length }}`],
    ['totalMs', 'number', `={{ Date.now() - ${V}.item.json.startedAt }}`],
    ['error', 'string', `={{ ${ran('Reply with error')} ? (${V}.item.json.error || 'could not transcribe') : ${ran('Reply with text')} ? 'TTS failed' : '' }}`],
    ['replyText', 'string', `={{ ${said}.reply : '') }}`]]);
  const orchestrator = finish({
    name: 'Northgate · Voice Loop', settings,
    nodes: [
      take('Voice request'), take('Validate request'), take('Request OK?'),
      take('New request?', { position: [660, 300] }), take('Seen before?', { position: [660, 100] }),
      take('Earlier answer', { position: [880, 100] }), take('Replay answer', { position: [1100, 100] }),
      take('Needs speech-to-text?', { position: [880, 300] }),
      call('Transcribe', [1100, 400], ids.transcribe, null),
      ifTrue('Heard it?', [1320, 400], '={{ $json.ok }}'),
      call('Receptionist', [1320, 220], ids.receptionist, [
        ['callerText', 'string', '={{ $json.text ?? $json.callerText }}'],
        ['sessionId', 'string', `={{ ${V}.item.json.sessionId }}`],
        ['requestId', 'string', `={{ ${V}.item.json.requestId }}`],
        ['simulate', 'string', `={{ ${V}.item.json.simulate }}`]]),
      replyToSpeak,
      call('Speak', [1760, 300], ids.speak, [
        ['reply', 'string', '={{ $json.reply }}'],
        ['sessionId', 'string', `={{ ${V}.item.json.sessionId }}`],
        ['simulate', 'string', `={{ ${V}.item.json.simulate }}`]]),
      ifTrue('Got audio?', [1980, 300], '={{ $json.ok }}'),
      audio, text, problem, logRow,
      take('Log request', { position: [2640, 400] }),
    ],
    connections: {
      'Voice request': to('Validate request'),
      'Validate request': to('Request OK?'),
      'Request OK?': to(['New request?', 'Seen before?'], 'Reply with error'),
      'Seen before?': to('Earlier answer'),
      'Earlier answer': to('Replay answer'),
      'Replay answer': to('Reply to speak'),
      'New request?': to('Needs speech-to-text?'),
      'Needs speech-to-text?': to('Transcribe', 'Receptionist'),
      'Transcribe': to('Heard it?'),
      'Heard it?': to('Receptionist', 'Reply with error'),
      'Receptionist': to('Reply to speak'),
      'Reply to speak': to('Speak'),
      'Speak': to('Got audio?'),
      'Got audio?': to('Reply with audio', 'Reply with text'),
      'Reply with audio': to('Log row'),
      'Reply with text': to('Log row'),
      'Reply with error': to('Log row'),
      'Log row': to('Log request'),
    },
    pinData: {},
  });
  return { transcribe, receptionist, speak, main: orchestrator };
}

// Stable form for fingerprinting: drop server-added ids/metadata, sort keys.
function canonical(wf) {
  const keep = ({ name, nodes, connections, settings, pinData }) => ({
    name, settings, pinData: pinData || {}, connections,
    nodes: nodes.map(({ id, webhookId, ...n }) => n).sort((a, b) => a.name.localeCompare(b.name)),
  });
  const sort = (x) => Array.isArray(x) ? x.map(sort)
    : x && typeof x === 'object' ? Object.fromEntries(Object.keys(x).sort().map((k) => [k, sort(x[k])])) : x;
  return JSON.stringify(sort(keep(wf)));
}

if (typeof module !== 'undefined') module.exports = { split, canonical };
