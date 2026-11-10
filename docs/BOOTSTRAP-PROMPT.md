# cutwright studio — one-shot setup prompt

**How to use this file**

1. Open a terminal on your friend's laptop, in an empty folder.
2. Start your coding agent (opencode, Claude Code, Codex — any agent that can run shell commands).
3. Fill the single credential line below, paste this whole file as the prompt, and let it run.
4. When it finishes, you get: `oc` (send work to the cloud box), `oc studio` (chat with opencode there), and a rendered test video.

```
E2B_API_KEY="<E2B_API_KEY>"
```

Nothing else needs a credential. No model keys, no GitHub token, no cloud login.

---

# THE PROMPT

You are a senior setup engineer. Build a working "video studio" on this laptop: a thin local
client, a persistent E2B cloud sandbox that does the rendering, and an opencode agent inside that
sandbox which can operate the cutwright video engine. Deliver a **running system with proof**, not
a plan and not a pile of scripts that were never executed.

## Non-negotiables

- **One secret.** The `E2B_API_KEY` above is the only credential. Do not ask for model API keys.
  Use opencode's free Zen models (`opencode/big-pickle`, fallbacks listed below). If they are
  unavailable without a key, stop at that exact point and report it — do not invent a workaround
  that needs another credential.
- **Idempotent.** Re-running must not create duplicate sandboxes, templates, or config.
- **Proof per phase.** Every phase ends with a command whose output demonstrates success. If a
  command fails, read the error, fix the cause, retry once, and if it still fails, stop and report
  the exact failing command and stderr. Do not silently continue.
- **Never echo the key.** No `set -x`, no logging it, no committing it, no putting it in a URL.
- **State lives in `~/.cutwright/`** (`state.json`, `config.env`, `sandbox/`), permissions 600.

## Phase 0 — preflight

Detect and report: OS, architecture, free disk, `node -v`, `python3 -V`, `git --version`,
`docker -v`. Requirements: Node ≥ 20, Python ≥ 3.10, ≥ 3 GB free disk.

- macOS: fine as-is.
- Linux: fine as-is.
- Windows: require WSL2 (Ubuntu). If not on WSL, stop and say so.
- Apple Silicon is fine; the sandbox is amd64.

Take the value from the credential line at the very top of this document and export it once for
this session. From here on refer to `$E2B_API_KEY` — do not paste the literal key into any other
file, and do not create a second placeholder.

```bash
export E2B_API_KEY="the value from the credential line at the top"
mkdir -p ~/.cutwright && chmod 700 ~/.cutwright
printf 'E2B_API_KEY="%s"\nCUTWRIGHT_TEMPLATE="cutwright-studio"\nCUTWRIGHT_TIMEOUT=3600\n' \
  "$E2B_API_KEY" > ~/.cutwright/config.env
chmod 600 ~/.cutwright/config.env
```

## Phase 1 — local client

```bash
python3 -m venv ~/.cutwright/venv
~/.cutwright/venv/bin/pip install --quiet --upgrade pip e2b==2.63.0
npm install -g @e2b/cli@2.23.0
```

Put `~/.cutwright/venv/bin` and npm's global bin on PATH in the shell profile, then verify:
`e2b --version` and `~/.cutwright/venv/bin/python -c "import e2b; print(e2b.__version__)"`.

Before writing SDK code, run this and **adapt to what it prints** — the Python argument names matter:

```bash
~/.cutwright/venv/bin/python - <<'EOF'
import inspect, e2b
print(inspect.signature(e2b.Sandbox.create))
print([m for m in dir(e2b.Sandbox) if not m.startswith('_')])
EOF
```

Expect `template=`, `timeout=`, `on_timeout=`, `auto_resume=` and methods `commands`, `files`,
`get_host`/`get_hostname`, `set_timeout`, `pause`, `kill`. If a name differs (for example
`on_timeout` vs `on_timeout_ms`), use the installed signature and note the difference in the final
report.

## Phase 2 — the cloud image

Create `~/.cutwright/sandbox/` and write these files exactly.

`e2b.Dockerfile`:

```dockerfile
FROM e2bdev/base:latest
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git xz-utils unzip \
      python3 python3-pip python3-venv \
      fonts-dejavu-core libegl1 libgl1 libglvnd0 libglx0 libx11-6 \
      libxcb1 libxau6 libxdmcp6 libbsd0 libmd0 libxext6 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g opencode-ai@1.19.5 skills@1.7.6 \
    && rm -rf /root/.npm

RUN curl -fsSL -o /tmp/ff.tar.xz \
      https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz \
    && tar -xJf /tmp/ff.tar.xz -C /tmp \
    && cp /tmp/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg /tmp/ffmpeg-master-latest-linux64-gpl/bin/ffprobe /usr/local/bin/ \
    && rm -rf /tmp/ff.tar.xz /tmp/ffmpeg-master-latest-linux64-gpl

RUN pip3 install --no-cache-dir --break-system-packages \
      numpy opencv-python-headless fonttools pillow skia-python

RUN git clone --depth 1 https://github.com/moiz-73/cutwright.git /opt/cutwright \
    && cd /opt/cutwright \
    && pip3 install --no-cache-dir --break-system-packages -e . \
    && python3 scripts/fetch_fonts.py

# craft skills: hyperframes, ffmpeg, three.js, plus the motion grammar file
RUN mkdir -p /opt/skills && cd /opt/skills \
    && npx -y skills@1.7.6 add heygen-com/hyperframes --agent '*' -y \
    && npx -y skills@1.7.6 add kajisho5/ffmpeg-skill --agent '*' -y \
    && npx -y skills@1.7.6 add CloudAI-X/threejs-skills --agent '*' -y \
    && curl -fsSL -o /opt/skills/MOTION-SPEC.md \
         https://raw.githubusercontent.com/nexu-io/motion-anything/main/MOTION-SPEC.md

COPY opencode.json /root/.config/opencode/opencode.json
COPY AGENTS.md /opt/cutwright/AGENTS.md
COPY start-oc.sh /usr/local/bin/start-oc
RUN chmod +x /usr/local/bin/start-oc \
    && mkdir -p /workspace/in /workspace/out \
    && cw doctor
```

`opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "opencode/big-pickle",
  "small_model": "opencode/mimo-v2.6-flash-free",
  "skills": ["/opt/skills"],
  "permission": { "bash": "allow", "edit": "allow", "webfetch": "allow" },
  "instructions": ["/opt/cutwright/AGENTS.md"]
}
```

`AGENTS.md` — this is what makes the agent cut like an editor instead of a slideshow generator:

```markdown
# Working rules for this box

You edit video with the `cw` CLI. Read `docs/RESEARCH.md` in /opt/cutwright before improvising.

## The five rules
1. Cuts land on the beat. Use `cw beats track.mp3` -> bpm + beat list; fit the grid, never
   accumulate rounded beat durations. `--cut-every 1` for montage, 2-4 for breathing room.
2. Exit is 40-50% of entrance. Elements start at 30-50% of the previous one. Stagger words
   60-120 ms, list rows 40-80 ms. Never linear easing.
3. Display type 4-9% of frame height; supporting text >= 32 px at 1080p. One accent word only.
4. Motion blur is a shutter: 3 samples over 180 degrees, clamped inside the shot. Never a
   CSS-style blur filter on moving type.
5. Mix to numbers: -14 LUFS integrated, <= -1 dBTP, hits +3..+6 dB over the bed.

## Commands
- `cw doctor` — toolchain check
- `cw launch --spec examples/lumen.json --out /workspace/out/launch.mp4 --crf 16`
- `cw hyper --out /workspace/out/hyper.mp4` — 3D beat-locked sting
- `cw edit /workspace/in/*.mp4 -o /workspace/out/cut.mp4 --target 30`
- `cw edit /workspace/in/*.mp4 -o /workspace/out/montage.mp4 --beats /workspace/in/music.mp3 --cut-every 2`
- `cw beats /workspace/in/music.mp3`
- `cw qc /workspace/out/cut.mp4 --expect '{"width":1920,"height":1080,"loudness":-14}'`

## Delivery
Always run `cw qc` on the output. If it fails, fix the render; never ship a failing file.
Report: output path, duration, resolution, LUFS, and the QC result.
```

`start-oc`:

```bash
#!/usr/bin/env bash
set -euo pipefail
PASS_FILE=/root/.oc-pass
[ -s "$PASS_FILE" ] || head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$PASS_FILE"
chmod 600 "$PASS_FILE"
export OPENCODE_SERVER_PASSWORD="$(cat "$PASS_FILE")"
exec opencode serve --hostname 0.0.0.0 --port 4096
```

Build it. Confirm the flag names first with `e2b template build --help`, then:

```bash
cd ~/.cutwright/sandbox
E2B_API_KEY="$(grep -oP '(?<=E2B_API_KEY=").*(?=")' ~/.cutwright/config.env)" \
  e2b template build --name cutwright-studio --dockerfile e2b.Dockerfile
```

If the CLI requires a config file instead of flags, create `e2b.toml` with `name` and
`dockerfile` and build from that. Record the resulting template name/id in `state.json`. Build
takes 5-15 minutes; stream the logs and do not proceed until the image builds and `cw doctor`
ran successfully inside it.

## Phase 3 — the connector `oc`

Write `~/.cutwright/bin/oc` (Python, executable, shebang the venv python) implementing:

```
oc up                 # create or reconnect; print id, state, remaining timeout
oc status             # running/paused, id, template, age
oc run "<task>"       # run opencode inside the box on a task, stream output
oc sh "<command>"     # run a raw shell command in the box, stream output
oc put <local> <dst>  # upload a file/dir (files are copied, dirs recursively)
oc get <src> <local>  # download a rendered file
oc studio             # interactive opencode TUI in the box (via e2b CLI if available)
oc sleep              # pause the sandbox (state kept, billing stops)
oc kill               # destroy the sandbox
oc logs               # last 200 lines of /workspace/oc.log
```

Behaviour requirements:

- **State**: `~/.cutwright/state.json` = `{"sandbox_id": ..., "template": ..., "created": ...}`.
  `oc up` connects if the id still exists (`Sandbox.connect`), otherwise creates a new one and
  rewrites state. A dead id must not wedge the CLI.
- **Lifetime**: create with `timeout=3600, on_timeout="pause", auto_resume=True` (adapt to the
  installed signature). Every `oc run`/`oc sh` calls `set_timeout(3600)` first, so the box stays
  alive while you work and pauses itself an hour after the last command.
- **Run**: `oc run` must execute
  `cd /workspace && opencode run --model "$OC_MODEL" "<task>"` and stream stdout live. Keep a
  copy in `/workspace/oc.log`. Default `OC_MODEL=opencode/big-pickle`; if the model is rejected,
  try in order `opencode/mimo-v2.6-flash-free`, then `opencode/big-pickle` with `--agent build`.
- **Transfers**: use the SDK file API with bytes, not shell heredocs, so binary media is safe.
- **Security**: never print the key; the sandbox password (if you use the HTTP server) is read
  from `/root/.oc-pass` through the SDK, never stored locally.

Add `oc` to PATH. Then prove the connector works:

```bash
oc up
oc sh "cw doctor && ffmpeg -version | head -1 && python3 -c 'import skia; print(\"skia ok\")'"
oc sh "ls /opt/skills | head"
```

## Phase 4 — 24/7 "on demand"

Explain in the final report, and encode in `oc`:

- E2B caps **continuous** runtime per plan: 1 h on Hobby, 24 h on Pro, custom on Enterprise.
  Pausing resets that window, and paused sandboxes are kept indefinitely with their filesystem and
  process state.
- Therefore "always available, never paying for idle" = **pause on idle, auto-resume on use**.
  That is exactly what `on_timeout="pause"` + `auto_resume=True` + `set_timeout(3600)` gives you.
- Add a belt-and-braces watchdog: a `oc sleep` call after 20 minutes of local inactivity via cron
  (macOS `launchd` or `crontab`, Linux `systemd --user`). Keep it optional and easy to remove.
- State the cost model plainly: you pay for running time only, so a 10-minute edit session costs
  minutes of a sandbox, not a month of a VPS.

If `Sandbox.create` rejects `auto_resume` on this SDK version, fall back to: `on_timeout="pause"`
plus an explicit `Sandbox.connect(id)` inside `oc up` (connect resumes paused sandboxes), and say
so in the report.

## Phase 5 — skills verification

The image installs three craft packs plus `MOTION-SPEC.md` under `/opt/skills`, and
`opencode.json` points at that directory. Verify inside the box:

```bash
oc sh "ls -d /opt/skills/*/ | wc -l && ls /opt/skills | head -20"
oc run "In one sentence, what does your motion.md say about shutter angle? Quote it."
```

A good answer quotes the 180-degree shutter rule. If the agent cannot see the skills, the path in
`opencode.json` is wrong — fix it and re-verify before continuing.

## Phase 6 — acceptance tests (all must pass)

1. **Render**: `oc run "Render the 3D sting at 640x360, no audio, to /workspace/out/test.mp4, then run cw qc on it."`
   then `oc get /workspace/out/test.mp4 ./test.mp4` and on the laptop
   `ffprobe -v error -show_entries format=duration -of csv=p=0 test.mp4` → `9.5`.
2. **Footage**: upload a short clip with `oc put`, run
   `oc run "cw edit /workspace/in/sample.mp4 -o /workspace/out/cut.mp4 --target 5 and qc it"`,
   download, confirm it plays and duration is ~5 s.
3. **Sleep/wake**: `oc sleep`, `oc status` → paused, `oc run "echo alive"` → resumes and prints
   `alive`, `oc status` → running.
4. **Survives a new shell**: open a fresh terminal, `oc status` still correct.
5. **Idempotent**: run `oc up` twice — same sandbox id, no duplicate.
6. **Local fallback**: `cw doctor` works on the laptop too if the user ever wants offline rendering
   (install ffmpeg + fonts + `pip install -e .` from a checkout; not required for cloud use).

## Phase 7 — hand-off

Write `~/cutwright-studio/README.md` with: the six commands, one worked example
("make a 15 s vertical cut with beat cuts from these three files"), how to stop billing
(`oc sleep` / `oc kill`), the plan limits, and the three most likely failures with fixes
(template build OOM, opencode model rejected, ffmpeg missing in PATH).

Then print a final report as a table: phase, command run, result (PASS/FAIL), and any deviation
from this prompt (SDK argument names, CLI flag names, model fallbacks). End with the exact commands
the human should type next.

---

## Notes for the human (not part of the prompt)

- **Repo:** Phase 2 clones `https://github.com/moiz-73/cutwright`, which is **public** — no token
  needed. If you fork it, replace the URL with your fork.
- **Plan:** on E2B Hobby the box can run 1 h continuously; it pauses and resumes transparently, so
  normal use is unaffected. A long single render (over an hour) needs Pro or a pause/resume chunking
  step.
- **Cost:** rendering is CPU-only inside the sandbox; the expensive part is wall-clock. A 21 s
  1080p film is ~3 min on 2 vCPU, so a session is cents, not dollars.
- **If the friend has no E2B account:** everything except the cloud part still works locally —
  `cw` runs on the laptop with ffmpeg + Python.
