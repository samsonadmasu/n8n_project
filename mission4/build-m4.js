// Builds the Mission 4 workflows from the Mission 3 workflow and prints their fingerprints.
// Run: node build-m4.js
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const { execFileSync } = require('child_process');
const { split, canonical } = require('./split.js');
execFileSync('python3', ['-I', path.join(__dirname, '../mission3/build-voice-m3.py')], { stdio: 'ignore' });
const m3 = JSON.parse(fs.readFileSync(path.join(__dirname, '../mission3/northgate-voice-m3.workflow.json'), 'utf8'));
const ids = JSON.parse(fs.readFileSync(path.join(__dirname, 'ids.json'), 'utf8'));
const out = split(m3, ids);
for (const [key, wf] of Object.entries(out)) {
  const file = { main: 'voice-loop', transcribe: 'transcribe', receptionist: 'receptionist', speak: 'speak' }[key];
  fs.writeFileSync(path.join(__dirname, `${file}.workflow.json`), JSON.stringify(wf, null, 2) + '\n');
  const hash = crypto.createHash('sha256').update(canonical(wf)).digest('hex').slice(0, 16);
  console.log(`${key.padEnd(12)} ${String(wf.nodes.length).padStart(2)} nodes  ${hash}`);
}
