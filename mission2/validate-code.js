// Cheap checks first: every rejected request here costs nothing downstream.
// Accepts a recording (form field "audio") or a typed turn (form field "message").
const MAX_BYTES = 5 * 1024 * 1024;   // ~5 minutes of speech
const MIN_BYTES = 1000;              // shorter than this is silence or a broken recording
const ALLOWED = ['audio/webm', 'video/webm', 'audio/mp4', 'audio/x-m4a', 'audio/m4a', 'audio/aac', 'audio/ogg', 'audio/mpeg', 'audio/wav', 'audio/x-wav'];

const item = $input.first();
const headers = item.json.headers || {};
const body = item.json.body || {};
const requestId = String(headers['x-request-id'] || $execution.id).slice(0, 80);
// One session = one conversation. The page sends the same id for every turn of a call.
const sessionId = String(headers['x-session-id'] || body.sessionId || '').replace(/[^\w.-]/g, '').slice(0, 80) || `req-${requestId}`;
const base = { requestId, sessionId, startedAt: Date.now() };
const reject = (error, extra = {}) => [{ json: { ...base, ok: false, status: 400, error, ...extra } }];

const bin = item.binary && item.binary.audio;
const typed = String(body.message || '').trim().slice(0, 1000);
if (!bin && typed) return [{ json: { ...base, ok: true, needsStt: false, callerText: typed, bytes: 0, mimeType: 'text/plain' } }];
if (!bin) return reject('No recording received. Send it as a form field named "audio", or type a "message".');

const mimeType = (bin.mimeType || '').split(';')[0].trim().toLowerCase();
const bytes = (await this.helpers.getBinaryDataBuffer(0, 'audio')).length;

if (bytes < MIN_BYTES) return reject(`The recording is empty or too short (${bytes} bytes). Speak for at least a second.`, { bytes, mimeType });
if (bytes > MAX_BYTES) return reject(`The recording is ${(bytes / 1048576).toFixed(1)} MB. The limit is 5 MB.`, { bytes, mimeType });
if (!ALLOWED.includes(mimeType)) return reject(`Audio type "${mimeType || 'unknown'}" isn't supported. Send webm, mp4/m4a, ogg, mp3 or wav.`, { bytes, mimeType });

return [{ json: { ...base, ok: true, needsStt: true, bytes, mimeType }, binary: item.binary }];
