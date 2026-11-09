"""cutwright command line."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from . import __version__


def _cmd_doctor(args) -> int:
    from .media import doctor

    info = doctor()
    print(json.dumps(info, indent=2))
    return 0 if info.get("ok") else 1


def _cmd_fonts(args) -> int:
    from . import fonts

    print(f"font dir: {fonts.FONT_DIR}")
    missing = 0
    for fam, weights in fonts._AVAILABLE.items():
        for w in weights:
            try:
                tf = fonts.typeface("serif-i" if fam == "InstrumentSerif" else fam.lower(), w)
                print(f"  ok   {tf.getFamilyName():20s} {w}")
            except Exception as e:
                missing += 1
                print(f"  MISS {fam} {w}: {e}")
    return 0 if not missing else 1


def _cmd_launch(args) -> int:
    from .comps import LaunchFilm, LaunchSpec
    from .render import RenderSettings, render_frames, render_still
    from .theme import Format

    spec = LaunchSpec.load(args.spec) if args.spec else LaunchSpec()
    fmt = Format(args.width, args.height, args.fps)
    film = LaunchFilm(spec, fmt)

    if args.still:
        for t in [float(x) for x in args.still.split(",")]:
            p = f"{args.out.rsplit('.', 1)[0]}-{t:05.2f}.png"
            render_still(film.draw, p, t, fmt.width, fmt.height)
            print(p)
        return 0

    settings = RenderSettings(
        fps=fmt.fps,
        motion_blur=args.motion_blur,
        shutter=args.shutter,
        crf=args.crf,
        preset=args.preset,
        grain=args.grain,
    )
    audio_path = None
    if not args.no_audio:
        audio_path = str(Path(tempfile.mkdtemp()) / "score.wav")
        film.soundtrack().write(audio_path)

    render_frames(
        film.draw,
        args.out,
        film.duration,
        fmt.width,
        fmt.height,
        settings,
        audio_path=audio_path,
        verbose=not args.quiet,
        t_clamp=film.clamp_time,
    )
    print(json.dumps({"out": args.out, "duration": film.duration, "size": [fmt.width, fmt.height]}))
    return 0


def _cmd_hyper(args) -> int:
    from .hyper import HyperFilm
    from .render import RenderSettings, render_frames, render_still
    from .theme import Format

    fmt = Format(args.width, args.height, args.fps)
    film = HyperFilm(fmt)
    if args.still:
        for t in [float(x) for x in args.still.split(",")]:
            p = f"{args.out.rsplit('.', 1)[0]}-{t:05.2f}.png"
            render_still(film.draw, p, t, fmt.width, fmt.height)
            print(p)
        return 0
    settings = RenderSettings(
        fps=fmt.fps, motion_blur=args.motion_blur, shutter=args.shutter,
        crf=args.crf, preset=args.preset, grain=args.grain,
    )
    audio_path = None
    if not args.no_audio:
        audio_path = str(Path(tempfile.mkdtemp()) / "score.wav")
        film.soundtrack().write(audio_path)
    render_frames(film.draw, args.out, film.duration, fmt.width, fmt.height, settings,
                  audio_path=audio_path, verbose=not args.quiet)
    print(json.dumps({"out": args.out, "duration": film.duration}))
    return 0


def _cmd_edit(args) -> int:
    from . import edit

    opt = edit.EditOptions(
        noise_db=args.noise_db,
        min_silence=args.min_silence,
        pad=args.pad,
        min_clip=args.min_clip,
        target_duration=args.target,
        vertical=args.vertical,
        width=args.width,
        height=args.height,
        fps=args.fps,
        crf=args.crf,
        preset=args.preset,
        loudness=args.loudness,
    )
    if args.beats:
        from . import beats as beatmod

        info = beatmod.analyze(args.beats)
        segs = edit.plan_beats(args.inputs, info["beats"], args.cut_every)
        print(f"beat montage: {info['bpm']} BPM, {len(info['beats'])} beats, {len(segs)} shots", file=sys.stderr)
    else:
        segs = edit.plan(args.inputs, opt)
    print(f"planned {len(segs)} segments, {sum(s.duration for s in segs):.2f}s -> {args.out}", file=sys.stderr)
    manifest = edit.render(segs, args.out, opt)
    print(json.dumps({"out": args.out, "segments": len(segs), "duration": manifest["duration"]}))
    return 0


def _cmd_beats(args) -> int:
    from . import beats

    r = beats.analyze(args.file)
    print(json.dumps({"bpm": r["bpm"], "beats": len(r["beats"]), "first": [round(x, 3) for x in r["beats"][:8]]}, indent=2))
    return 0


def _cmd_probe(args) -> int:
    from .media import probe

    print(json.dumps(probe(args.file), indent=2))
    return 0


def _cmd_qc(args) -> int:
    from . import qc

    expect = json.loads(args.expect) if args.expect else None
    r = qc.report(args.file, args.json, expect)
    for c in r["checks"]:
        print(f"  {'PASS' if c['ok'] else 'FAIL'}  {c['check']:16s} {c['detail']}")
    print(f"{'PASSED' if r['passed'] else 'FAILED'}  {args.file}")
    return 0 if r["passed"] else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cw", description="Deterministic launch films and footage edits.")
    p.add_argument("--version", action="version", version=f"cutwright {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="check ffmpeg and encoders")
    d.set_defaults(func=_cmd_doctor)

    f = sub.add_parser("fonts", help="verify the bundled type stack")
    f.set_defaults(func=_cmd_fonts)

    l = sub.add_parser("launch", help="render a launch film")
    l.add_argument("--spec", help="brand/copy JSON")
    l.add_argument("--out", default="out/launch.mp4")
    l.add_argument("--width", type=int, default=1920)
    l.add_argument("--height", type=int, default=1080)
    l.add_argument("--fps", type=int, default=30)
    l.add_argument("--crf", type=int, default=17)
    l.add_argument("--preset", default="medium")
    l.add_argument("--motion-blur", type=int, default=3)
    l.add_argument("--shutter", type=float, default=0.5)
    l.add_argument("--grain", type=float, default=4.0)
    l.add_argument("--still", help="comma-separated times to export PNG stills")
    l.add_argument("--no-audio", action="store_true")
    l.add_argument("--quiet", action="store_true")
    l.set_defaults(func=_cmd_launch)

    h = sub.add_parser("hyper", help="render the beat-locked 3D sting")
    h.add_argument("--out", default="out/hyper.mp4")
    h.add_argument("--width", type=int, default=1920)
    h.add_argument("--height", type=int, default=1080)
    h.add_argument("--fps", type=int, default=30)
    h.add_argument("--crf", type=int, default=17)
    h.add_argument("--preset", default="medium")
    h.add_argument("--motion-blur", type=int, default=3)
    h.add_argument("--shutter", type=float, default=0.5)
    h.add_argument("--grain", type=float, default=4.0)
    h.add_argument("--still")
    h.add_argument("--no-audio", action="store_true")
    h.add_argument("--quiet", action="store_true")
    h.set_defaults(func=_cmd_hyper)

    e = sub.add_parser("edit", help="auto-edit footage")
    e.add_argument("inputs", nargs="+")
    e.add_argument("-o", "--out", default="out/edit.mp4")
    e.add_argument("--vertical", action="store_true")
    e.add_argument("--width", type=int, default=1920)
    e.add_argument("--height", type=int, default=1080)
    e.add_argument("--fps", type=int, default=30)
    e.add_argument("--crf", type=int, default=18)
    e.add_argument("--preset", default="medium")
    e.add_argument("--noise-db", type=float, default=-32.0)
    e.add_argument("--min-silence", type=float, default=0.35)
    e.add_argument("--pad", type=float, default=0.07)
    e.add_argument("--min-clip", type=float, default=0.45)
    e.add_argument("--target", type=float, default=None)
    e.add_argument("--loudness", type=float, default=-14.0)
    e.add_argument("--beats", help="audio file: cut the montage on its beat grid")
    e.add_argument("--cut-every", type=int, default=2, help="beats per shot (with --beats)")
    e.set_defaults(func=_cmd_edit)

    bt = sub.add_parser("beats", help="detect tempo and beats in an audio file")
    bt.add_argument("file")
    bt.set_defaults(func=_cmd_beats)

    pr = sub.add_parser("probe", help="inspect a media file")
    pr.add_argument("file")
    pr.set_defaults(func=_cmd_probe)

    q = sub.add_parser("qc", help="run quality gates on an output")
    q.add_argument("file")
    q.add_argument("--json")
    q.add_argument("--expect", help='e.g. {"width":1920,"height":1080,"duration":21}')
    q.set_defaults(func=_cmd_qc)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
