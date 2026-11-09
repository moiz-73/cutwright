"""Footage auto-editor: remove dead air, tighten to scenes, reframe, render once."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from . import analyze
from .media import probe, run
from .render import ffmpeg_bin


@dataclass
class EditOptions:
    noise_db: float = -32.0
    min_silence: float = 0.35
    pad: float = 0.07
    min_clip: float = 0.45
    target_duration: float | None = None
    vertical: bool = False
    width: int = 1920
    height: int = 1080
    fps: int = 30
    crf: int = 18
    preset: str = "medium"
    loudness: float = -14.0
    fade_in: float = 0.25
    fade_out: float = 0.35
    keep_silence_before: float = 0.12


@dataclass
class Segment:
    src: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def _merge(spans: list[tuple[float, float]], gap: float = 0.08) -> list[tuple[float, float]]:
    if not spans:
        return []
    spans = sorted(spans)
    out = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def plan_for(path: str, opt: EditOptions) -> list[Segment]:
    info = probe(path)
    dur = info["duration"]
    sil = analyze.silences(path, opt.noise_db, opt.min_silence)

    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for s, e in sil:
        s2 = min(dur, s + opt.pad)
        e2 = max(0.0, e - opt.keep_silence_before)
        if s2 > cursor:
            keep.append((cursor, s2))
        cursor = max(cursor, min(dur, e2))
    if cursor < dur:
        keep.append((cursor, dur))

    keep = [(s, e) for s, e in _merge(keep) if e - s >= opt.min_clip]
    if not keep:
        keep = [(0.0, dur)]

    segs = [Segment(path, s, e) for s, e in keep]
    if opt.target_duration:
        acc, trimmed = 0.0, []
        for seg in segs:
            if acc >= opt.target_duration:
                break
            room = opt.target_duration - acc
            if seg.duration > room and room > opt.min_clip:
                seg = Segment(seg.src, seg.start, seg.start + room)
            trimmed.append(seg)
            acc += seg.duration
        segs = trimmed
    return segs


def plan_beats(sources: list[str], beat_times: list[float], every: int = 2) -> list[Segment]:
    """Montage: one shot per `every` beats, cycling sources, cuts on the grid."""
    if not beat_times or len(beat_times) < every + 1:
        raise ValueError("not enough beats detected")
    infos = {s: probe(s) for s in sources}
    cursors = {s: 0.0 for s in sources}
    segs: list[Segment] = []
    for i in range(0, len(beat_times) - every, every):
        a, b = beat_times[i], beat_times[i + every]
        dur = min(1.2, max(0.18, b - a))
        src = sources[(i // every) % len(sources)]
        total = infos[src]["duration"]
        if total <= dur:
            segs.append(Segment(src, 0.0, total))
            continue
        start = cursors[src] % max(0.01, total - dur)
        segs.append(Segment(src, start, start + dur))
        cursors[src] = start + dur + 0.05
    return segs


def plan(sources: list[str], opt: EditOptions) -> list[Segment]:
    segs: list[Segment] = []
    for s in sources:
        segs.extend(plan_for(s, opt))
    return segs


def _video_chain(opt: EditOptions) -> str:
    if opt.vertical:
        return (
            f"scale={opt.width}:{opt.height}:force_original_aspect_ratio=increase,"
            f"crop={opt.width}:{opt.height},setsar=1,fps={opt.fps}"
        )
    return (
        f"scale={opt.width}:{opt.height}:force_original_aspect_ratio=increase,"
        f"crop={opt.width}:{opt.height},setsar=1,fps={opt.fps}"
    )


def render(segments: list[Segment], out_path: str, opt: EditOptions) -> dict:
    if not segments:
        raise ValueError("empty edit plan")
    inputs: list[str] = []
    idx: dict[str, int] = {}
    for seg in segments:
        if seg.src not in idx:
            idx[seg.src] = len(inputs)
            inputs.append(seg.src)

    total = sum(s.duration for s in segments)
    parts: list[str] = []
    labels: list[str] = []
    for i, seg in enumerate(segments):
        src_i = idx[seg.src]
        info = probe(seg.src)
        parts.append(
            f"[{src_i}:v]trim=start={seg.start:.4f}:end={seg.end:.4f},setpts=PTS-STARTPTS,"
            f"{_video_chain(opt)}[v{i}]"
        )
        if info["has_audio"]:
            parts.append(
                f"[{src_i}:a]atrim=start={seg.start:.4f}:end={seg.end:.4f},asetpts=PTS-STARTPTS,"
                f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]"
            )
        else:
            parts.append(f"aevalsrc=0:d={seg.duration:.4f}:s=48000:c=stereo[a{i}]")
        labels.append(f"[v{i}][a{i}]")

    fade_out_start = max(0.0, total - opt.fade_out - 0.05)
    parts.append(
        "".join(labels)
        + f"concat=n={len(segments)}:v=1:a=1[cv][ca]"
    )
    parts.append(
        f"[cv]fade=t=in:st=0:d={opt.fade_in:.3f},"
        f"fade=t=out:st={fade_out_start:.3f}:d={opt.fade_out:.3f}[vout]"
    )
    parts.append(
        f"[ca]afade=t=in:st=0:d={opt.fade_in:.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={opt.fade_out:.3f},"
        f"loudnorm=I={opt.loudness}:TP=-1.5:LRA=11[aout]"
    )

    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y"]
    for p in inputs:
        cmd += ["-i", p]
    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", opt.preset, "-crf", str(opt.crf),
        "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
        "-movflags", "+faststart", "-t", f"{total:.3f}", out_path,
    ]
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    res = run(cmd, timeout=3600)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg edit failed:\n{res.stderr[-3000:]}")

    manifest = {
        "sources": inputs,
        "segments": [asdict(s) for s in segments],
        "duration": round(total, 3),
        "options": asdict(opt),
        "out": out_path,
    }
    Path(out_path).with_suffix(".plan.json").write_text(json.dumps(manifest, indent=2))
    return manifest
