# Research: what actually makes high-end video on a 2-vCPU box

This is the evidence behind cutwright's design. It covers three layers — Harness
plugins, agent skills, and render/edit engines — plus the 3D question, with
measured numbers from this machine (2 vCPU, 1.9 GB RAM, no GPU, Debian 12,
Python 3.11, Node 22).

Method: Exa searches, GitHub API verification of every candidate (stars,
licence, last commit), and hands-on installs/benchmarks rather than README
claims. Numbers marked "measured" were produced on this box.

---

## 1. The Harness plugin layer is plumbing, not pixels

- The live Harness profile exposes **194 config rows across 20 bundles**. None
  is a video, image or 3D renderer.
- `awesome-dsh-plugin` carries **9,687 plugin manifests**; keyword-matching
  video/media/3D/ffmpeg yields **~99**, and most are provider wrappers.
- `dsh-plugin.org`'s "22,137 verified plugins" is a GitHub-topic count from a
  scraper, not a capability index.

Seven projects were audited at source level:

| Project | What it does locally | Verdict |
|---|---|---|
| dsh-media-gen | **zero ffmpeg calls**; OpenAI/Gemini/DashScope/Volcengine endpoints | 100% of cost, 0% of pixels |
| dsh-videogen | thin `-preset veryfast -crf 23` wrappers | not installable (no `lib/`, not on npm) |
| dsh-directorx | real timeline: trims, xfade, ducking, 16 grades | 111 MB / 1,101 files / 153 tools; `veryfast` + default CRF every pass |
| yingliu-video-studio | Chrome frame capture, CRF 16/18, limiter, frame-count QA | GPL-3.0, Desktop-leaning, no motion blur |
| dsh-genbox | 11 ffmpeg ops behind a second service | `veryfast`, no CRF |
| hyperframes | best-in-class HTML→MP4, BeginFrame seek, real motion blur | needs Chrome; **fails its own memory check at 1.9 GB** |
| dsh-hyperframes | re-packages upstream skills | redundant mirror |

**Conclusion:** no installable Harness plugin raises render quality. The quality
lever is the renderer, the motion system, and the QC loop — so cutwright owns
those and treats ffmpeg as the encoder, not the editor.

## 2. Agent skills — installed, and what they are worth

Skills ship craft knowledge and tool contracts, not pixels. Installed with
`npx -y skills@1.7.6 add <repo> --agent '*' -y` into `research/.agents/skills`:

| Pack | Skills | Size | What it actually adds |
|---|---|---|---|
| heygen-com/hyperframes | 9 | 4.2 MB | `motion.md`, `look.md`, `sound.md` with measured thresholds; storyboard schema |
| kajisho5/ffmpeg-skill | 42 tools | ~2 MB | machine-readable ffmpeg contracts, `--dry-run/--json`, loudnorm recipes |
| CloudAI-X/threejs-skills | 13 | 340 KB | pinned three r186 / R3F 9.8, shaders, postprocessing |
| **total** | **23 dirs** | **32 MB** | |

Rejected: `remotion-dev/skills` (no licence file, paid licence above 3
employees, and rendering exceeds this box's RAM), `video-shotcraft` (64 MB,
Remotion-based), and every GUI-app MCP (Blender/FreeCAD/GIMP/Krita) — the apps
are not installable here at 1.9 GB.

## 3. Engine benchmarks — where the CPU actually goes

180 frames of 1080p through ffmpeg 2026 static build, 2 vCPU:

| Operation | fps | ms/frame | Note |
|---|---|---|---|
| decode only (baseline) | 40.7 | 24.6 | |
| x264 ultrafast | 36.9 | 27.1 | |
| grade: eq + curves + lut3d | **12.3** | **81.3** | OpenCV LUT path costs 15 ms |
| gblur σ=12 | 45.2 | 22.1 | |
| rgbashift | 52.6 | 19.0 | |
| noise grain | 61.9 | 16.2 | why grain is applied in-loop |
| scdet | 47.3 | 21.2 | |
| xfade (fade / smoothleft / zoomin / hblur / pixelize) | 39–30 | 25–34 | cheap enough for beat cuts |
| deshake | 4.4 | 225.4 | unusable |
| **minterpolate (mci 30→60)** | **0.48** | **2,070.8** | never |

Python detectors, same box:

| Tool | Cost | Note |
|---|---|---|
| PySceneDetect (content/adaptive/hash/threshold) | ~1.3–1.5 s per 6 s clip, 123–137 fps | usable |
| librosa beat tracking | **13.5 s for 6 s audio** (2.2× realtime) | too heavy for a CLI edit |
| aubio onset | 0.13 s | fast, but no grid refinement |
| **cutwright `beats.py` (numpy flux + autocorr + LSQ)** | **~0.2 s** | adopted |

Decision: keep frames in Skia/OpenCV, use ffmpeg only for encode/mux. The 81 ms
ffmpeg grade chain versus 15 ms `cv2.LUT` + `cv2.transform` is the clearest
example — the filter graph is not the fast path at 1080p.

## 4. 3D: what is actually reachable

| Route | Reality on this box |
|---|---|
| Blender headless | apt install failed (truncated package archives); even fixed, Cycles CPU is tens of seconds per 1080p frame, EEVEE needs a GL context |
| Chrome + three.js (SwiftShader) | Chromium exists, but HyperFrames' own doctor fails the 1.9 GB memory check; frame capture is slow and RAM-bound |
| **Skia projective compositor** | built: perspective projection, painter sort, textured and *vector-text* planes, flat-shaded meshes, floor grids |

`threed.py` cost per 1080p comp: **176–257 ms**, dominated by perspective text
(glyph runs transformed by a projective matrix) and grid lines. It is not a
replacement for Blender for hero 3D assets; it is the right tool for 3D
*typography and camera language*, which is what a launch sting needs.

The interesting primitive: drawing **vector text through the projective
matrix** rather than warping a bitmap. No resampling, no texture memory, and it
composites correctly over the grid.

## 5. Craft rules → code

From the skill references (HyperFrames `motion.md`/`sound.md`, video-shotcraft
aesthetic rules, NN/g and Carbon motion tokens), encoded as constants:

| Rule | Constant | Where |
|---|---|---|
| Beat grid must be fitted, not accumulated | `t_i = a + i·T` least squares over onset peaks, reject if residual > 45 ms | `beats.refine()` |
| Montage cuts 0.13–0.8 s; shots 1.8–3 s | `plan_beats` clamps shot length to 0.18–1.2 s | `edit.plan_beats()` |
| Stagger words 60–120 ms / items 40–80 ms | 100 ms per feature row | `comps._features` |
| Readable auxiliary type ≥ 32 px @1080 | 27–30 px body raised to 30.7–33.6 px | `comps.py` |
| Blur is a shutter, not a filter | 3 sub-frames, 180°, clamped per shot | `render.render_frames`, `LaunchFilm.clamp_time` |
| Mix to numbers | −14 LUFS integrated, −1.5 dBTP, hits +3–6 dB over bed | `render._mux`, `hyper.soundtrack` |
| Never crossfade at a cut | hard cuts at every scene boundary | `comps.STARTS` |

Effect of the first rule, measured: a 128 BPM click track was detected at
**129.2 BPM** with a comb grid and **128.18 BPM** after least-squares refinement
(25 beats, constant 0.468 s spacing).

Effect of the type rule: the LUMEN master was re-rendered because descriptions
sat at 27 px — legible on a monitor, not on a phone.

## 6. Measured outputs

| Render | Frames | Time on 2 vCPU | Size | QC |
|---|---|---|---|---|
| LUMEN launch film, 21 s 1080p30, 3 shutter samples | 630 | 165 s | 29 MB | pass |
| HYPERCUT 3D sting, 9.5 s 1080p30, 3 shutter samples | 285 | 560 s | 12 MB | pass |
| Footage auto-edit, 18 s → 11.07 s | — | 38 s | 13 MB | pass |
| Beat montage, 26 beats → 11.15 s / 12 shots | — | 44 s | 13 MB | pass |

HYPERCUT is the expensive one because every frame redraws a 54-line grid, 56
speed streaks, and perspective text three times for motion blur. The next
optimisation is caching glyph runs as layers rather than re-transforming them
per sample.

## 7. Deliberately not adopted

- Neural video generation (Wan/Kling/Sora/Veo): $0.25–$2.50 per 5 s clip at
  list, 2–3× with retries, and none of it is local.
- VBench / VideoScore / DOVER / aesthetic predictors: need torch and several GB
  of VRAM; deterministic QC (peak-luminance, freezes, LUFS, true peak, exact
  frame count) substitutes at zero cost.
- `minterpolate`, `deshake`, `tmix`-based fake motion blur: 2,071 ms, 225 ms,
  and visibly wrong respectively.
- Blender/CAD MCP bridges: the applications cannot run here.
- The 9,600-entry plugin index: 99% is provider plumbing.

## 8. Where the next quality is

1. **Cache 3D text as layers** — removes most of the 560 s in HYPERCUT.
2. **xfade at beat seams** — 25–34 ms/frame is affordable, and whip/zoom
   transitions are the missing vocabulary between hard cuts and dissolves.
3. **OTIO as the EDL format** — `pip install opentimelineio` works; it would
   let the cut be opened in Kdenlive/Resolve instead of only re-rendered.
4. **A hero-shot pass through Blender** on a machine with ≥8 GB, composited as
   an RGBA plane — `threed.Plane(image=...)` already accepts it.
