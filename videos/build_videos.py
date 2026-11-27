"""Build one narrated walkthrough video per Northgate workflow.

    python3 build_videos.py <frames-dir> [script-name ...]
    VOICE_ENGINE=elevenlabs python3 build_videos.py <frames-dir>     # narrate with your cloned voice

Each script in videos/scripts/ is a title line plus blocks of
    [frame: <name>]
    narration text...
Frames named n-<stem> are screenshots of open n8n nodes, <frames-dir>/ndv/<stem>.jpg (800x450 from the
browser pane at a 1024x576 viewport). Sensitive fields (webhook addresses, the Pushover user key) are
blacked out via REDACT before anything is encoded.

Voices:
  say         macOS voice (default) - for quick previews
  elevenlabs  your ElevenLabs voice clone. Needs videos/.env with ELEVENLABS_API_KEY (git-ignored) and a
              voice named VOICE_NAME. Audio is cached in videos/.cache/ by text, so re-runs cost nothing.

Output: videos/<script-name>.mp4 (git-ignored). Needs ffmpeg, macOS `say`, and Google Chrome (title cards).
"""
import hashlib, json, os, pathlib, subprocess, sys, tempfile, urllib.request

HERE = pathlib.Path(__file__).parent
ENGINE = os.environ.get('VOICE_ENGINE', 'say')
SAY_VOICE, SAY_RATE = 'Daniel', '168'
VOICE_NAME = os.environ.get('VOICE_NAME', 'Samson narration')
ELEVEN_MODEL = 'eleven_multilingual_v2'
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
ACCENT, BG = '0x2dd4bf', '0x121615'

# Node screens: crop off n8n's promo banner (top 30 px) and the collapsed-sidebar marks (left 10 px).
NDV_CROP = (10, 30, 790, 420)  # x, y, w, h in the 800x450 screenshot
# Fields that must never appear in a video, in 800x450 screenshot coordinates.
REDACT = {
    'voice-webhook':       [(283, 188, 532, 224)],   # webhook address
    'tools-check-webhook': [(283, 188, 532, 238)],   # webhook address
    'rec-create-booking':  [(269, 308, 507, 335)],   # tool URL
    'alerts-push':         [(269, 304, 531, 332)],   # Pushover user key
}


def run(*cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def duration(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
                         check=True, capture_output=True, text=True).stdout
    return float(out)


HI_CROP = (24, 0, 2024, 1138)  # 2048x1152 captures: trim the sidebar edge, keep 16:9


def frame_png(frames_dir, name, out):
    if not name.startswith('n-'):
        raise ValueError(f'unknown frame {name}')
    stem = name[2:]
    hi = frames_dir / 'hi' / f'{stem}.png'
    if hi.exists():
        # Full-resolution capture (2x pixel density). Sensitive fields were covered in the browser before capture.
        x, y, w, h = HI_CROP
        run('ffmpeg', '-loglevel', 'error', '-y', '-i', str(hi), '-vf',
            f'crop={w}:{h}:{x}:{y},scale=1920:1080:flags=lanczos,format=yuv420p', '-frames:v', '1', str(out))
        return
    src = frames_dir / 'ndv' / f'{stem}.jpg'
    x0, y0, w0, h0 = NDV_CROP
    scale = 1920 / w0
    height = round(h0 * scale) // 2 * 2
    pad_top = (1080 - height) // 2
    boxes = []
    for x1, y1, x2, y2 in REDACT.get(stem, []):
        X, Y = round((x1 - x0) * scale), round((y1 - y0) * scale) + pad_top
        W, H = round((x2 - x1) * scale), round((y2 - y1) * scale)
        boxes.append(f"drawbox=x={X}:y={Y}:w={W}:h={H}:color=0x1b211f:t=fill,"
                     f"drawbox=x={X}:y={Y}:w={W}:h={H}:color={ACCENT}@0.8:t=3")
    vf = f"crop={w0}:{h0}:{x0}:{y0},scale=1920:{height}:flags=lanczos,pad=1920:1080:0:{pad_top}:color={BG}"
    vf = ','.join([vf] + boxes + ['format=yuv420p'])
    run('ffmpeg', '-loglevel', 'error', '-y', '-i', str(src), '-vf', vf, '-frames:v', '1', str(out))


def title_card(title, subtitle, out, tmp):
    html = tmp / 'title.html'
    html.write_text(f"""<!doctype html><meta charset="utf-8"><style>
    html,body{{margin:0;width:1280px;height:720px;background:#111614;color:#e5ece8;font-family:-apple-system,Helvetica,sans-serif}}
    body{{display:flex;flex-direction:column;justify-content:center;padding:0 120px;box-sizing:border-box;
         background-image:radial-gradient(#222b27 1.4px,transparent 1.4px);background-size:26px 26px}}
    .k{{font:600 20px Menlo,monospace;letter-spacing:.12em;color:#2dd4bf;text-transform:uppercase}}
    h1{{font-size:72px;margin:18px 0 14px;letter-spacing:-.02em}} p{{font-size:28px;color:#9ba8a2;margin:0}}
    </style><div class="k">Northgate Voice Desk · n8n workflow</div><h1>{title}</h1><p>{subtitle}</p>""")
    png = tmp / 'title.png'
    run(CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1.5',
        '--window-size=1280,720', f'--screenshot={png}', f'file://{html}')
    run('ffmpeg', '-loglevel', 'error', '-y', '-i', str(png), '-vf', 'scale=1920:1080,format=yuv420p', str(out))


# ---- narration ------------------------------------------------------------------------------
def _eleven_key():
    env = HERE / '.env'
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith('ELEVENLABS_API_KEY='):
            return line.split('=', 1)[1].strip()
    sys.exit('VOICE_ENGINE=elevenlabs needs ELEVENLABS_API_KEY in videos/.env')


def _eleven(path, key, body=None):
    req = urllib.request.Request(f'https://api.elevenlabs.io{path}', data=json.dumps(body).encode() if body else None,
                                 headers={'xi-api-key': key, 'Content-Type': 'application/json'},
                                 method='POST' if body else 'GET')
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


_voice_id = None


def eleven_voice_id(key):
    global _voice_id
    if _voice_id is None:
        voices = json.loads(_eleven('/v1/voices', key))['voices']
        match = [v for v in voices if v['name'].strip().lower() == VOICE_NAME.lower()]
        if not match:
            sys.exit(f'No ElevenLabs voice named "{VOICE_NAME}". Found: {", ".join(v["name"] for v in voices)}')
        _voice_id = match[0]['voice_id']
    return _voice_id


def narrate(text, wav, tmp):
    if ENGINE == 'say':
        (tmp / 'line.txt').write_text(text)
        run('say', '-v', SAY_VOICE, '-r', SAY_RATE, '-o', str(tmp / 'line.aiff'), '-f', str(tmp / 'line.txt'))
        src = tmp / 'line.aiff'
    else:
        key = _eleven_key()
        vid = eleven_voice_id(key)
        cache = HERE / '.cache'
        cache.mkdir(exist_ok=True)
        src = cache / (hashlib.sha256(f'{vid}|{ELEVEN_MODEL}|{text}'.encode()).hexdigest()[:24] + '.mp3')
        if not src.exists():
            audio = _eleven(f'/v1/text-to-speech/{vid}?output_format=mp3_44100_128', key, {
                'text': text, 'model_id': ELEVEN_MODEL,
                'voice_settings': {'stability': 0.5, 'similarity_boost': 0.85, 'style': 0.0, 'use_speaker_boost': True}})
            src.write_bytes(audio)
    run('ffmpeg', '-loglevel', 'error', '-y', '-i', str(src), '-ar', '44100', '-ac', '1', str(wav))


def clip(png, wav, out, seconds):
    run('ffmpeg', '-loglevel', 'error', '-y', '-loop', '1', '-framerate', '30', '-i', str(png), '-i', str(wav),
        '-filter_complex', '[1:a]apad=pad_dur=0.6[a];[0:v]fade=t=in:st=0:d=0.25,format=yuv420p[v]',
        '-map', '[v]', '-map', '[a]', '-t', f'{seconds:.2f}', '-c:v', 'libx264', '-preset', 'medium',
        '-tune', 'stillimage', '-crf', '20', '-c:a', 'aac', '-b:a', '160k', '-ar', '44100', '-ac', '2', str(out))


def silent_wav(out, seconds):
    run('ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono', '-t', str(seconds), str(out))


def parse(path):
    lines = path.read_text().splitlines()
    title = lines[0].split(':', 1)[1].strip()
    blocks, frame, text = [], None, []
    for line in lines[1:]:
        if line.startswith('[frame:'):
            if frame:
                blocks.append((frame, ' '.join(text)))
            frame, text = line.split(':', 1)[1].strip(' ]'), []
        elif line.strip():
            text.append(line.strip())
    blocks.append((frame, ' '.join(text)))
    return title, blocks


def build(script, frames_dir):
    title, blocks = parse(script)
    out = HERE / f'{script.stem}.mp4'
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        clips = []
        title_card(title.replace('Northgate · ', ''), 'Inside the workflow, node by node', tmp / 'title-frame.png', tmp)
        silent_wav(tmp / 'title.wav', 0.1)
        clip(tmp / 'title-frame.png', tmp / 'title.wav', tmp / 'c00.mp4', 2.5)
        clips.append(tmp / 'c00.mp4')
        for i, (frame, text) in enumerate(blocks, 1):
            narrate(text, tmp / f'n{i}.wav', tmp)
            frame_png(frames_dir, frame, tmp / f'f{i}.png')
            clip(tmp / f'f{i}.png', tmp / f'n{i}.wav', tmp / f'c{i:02d}.mp4', duration(tmp / f'n{i}.wav') + 0.6)
            clips.append(tmp / f'c{i:02d}.mp4')
        (tmp / 'list.txt').write_text(''.join(f"file '{c}'\n" for c in clips))
        run('ffmpeg', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(tmp / 'list.txt'),
            '-c', 'copy', '-movflags', '+faststart', str(out))
    return out, duration(out)


if __name__ == '__main__':
    frames_dir = pathlib.Path(sys.argv[1])
    wanted = set(sys.argv[2:])
    print(f'voice: {ENGINE}' + (f' ({VOICE_NAME})' if ENGINE == 'elevenlabs' else f' ({SAY_VOICE})'))
    for script in sorted((HERE / 'scripts').glob('*.txt')):
        if wanted and script.stem not in wanted:
            continue
        out, secs = build(script, frames_dir)
        print(f'{out.name:28} {int(secs) // 60}:{int(secs) % 60:02d}  {out.stat().st_size / 1e6:.1f} MB')
