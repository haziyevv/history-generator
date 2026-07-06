"""Command-line interface: `python -m historygen <command>`.

Commands:
  new "<topic>" [--genre auto|historical|sociological] [--language X] [--gender male|female]
                [--orientation vertical|horizontal|square] [--minutes N]
                          create a project + generate the script (review checkpoint).
                          Any topic works — genre defaults to 'auto' (model picks the style).
  run <slug>             run the full pipeline (resumable; skips fresh stages)
  run <slug> --stage X   run only stage X (script|narration|visuals|captions|music|assemble)
  run <slug> --force     ignore the cache and regenerate everything
  status <slug>          print the project's current state
  list                   list all projects
  translate <slug> "<topic>" [--language X]
                          clone a finished project into another language,
                          reusing its visuals (default language: English)
"""

from __future__ import annotations

import argparse
import sys

from historygen.config import PROJECTS_DIR, SETTINGS, apply_project_render
from historygen.manifest import Manifest
from historygen.pipeline import STAGE_NAMES, run_all
from historygen.schemas import Genre
from historygen.stages import captions, music, narration, script, translate
from historygen.stages import assemble as assemble_stage


def _cmd_new(args: argparse.Namespace) -> int:
    manifest = Manifest.create(args.topic)
    if args.language:
        manifest.project.language = args.language
    if args.gender:
        manifest.project.voice_gender = args.gender
    if args.genre:
        manifest.project.genre = Genre(args.genre)
    if args.orientation:
        manifest.project.orientation = args.orientation
    if args.minutes:
        manifest.project.target_seconds = int(round(args.minutes * 60))
    manifest.save()
    print(f"Created project '{manifest.slug}' at {manifest.dir}")
    script.run(manifest)
    print(
        f"\nReview the script at:\n  {manifest.path}\n"
        f"Edit scene narration/visuals if you like, then run:\n"
        f"  python -m historygen run {manifest.slug}"
    )
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    manifest = Manifest.load(args.slug)
    if args.stage and args.stage not in STAGE_NAMES:
        print(f"Unknown stage '{args.stage}'. Choose from: {', '.join(STAGE_NAMES)}")
        return 2
    # Apply voice gender/language overrides before running (clears locked voice_id).
    if args.gender or args.language:
        if args.gender:
            manifest.project.voice_gender = args.gender
        if args.language:
            manifest.project.voice_language = args.language
        manifest.project.voice_id = None  # force re-pick with new settings
        manifest.save()
    run_all(manifest, only=args.stage, force=args.force)
    if manifest.project.final_video:
        print(f"\nFinal video: {manifest.project.final_video}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    manifest = Manifest.load(args.slug)
    p = manifest.project
    print(f"Project: {p.slug}")
    print(f"Topic:   {p.topic}")
    print(f"Genre:   {p.genre.value}")
    print(f"Format:  {p.orientation}, ~{p.target_seconds}s")
    print(f"Title:   {p.title or '(not generated)'}")
    print(f"Scenes:  {len(p.scenes)}")
    print(f"Stages done: {', '.join(manifest.stage_cache) or '(none)'}")
    print(f"Final:   {p.final_video or '(not rendered)'}")
    print("\nService keys configured:")
    for svc in ("anthropic", "elevenlabs", "openai"):
        print(f"  {svc:12} {'yes' if SETTINGS.has(svc) else 'NO (placeholder mode)'}")
    return 0


def _cmd_translate(args: argparse.Namespace) -> int:
    manifest = translate.clone_translated(args.slug, args.topic, args.language)
    apply_project_render(manifest.project.orientation, manifest.project.target_seconds)
    print(
        f"\nCreated '{manifest.slug}'. Now generating narration/captions/music/assemble..."
    )
    narration.run(manifest)
    captions.run(manifest)
    music.run(manifest)
    assemble_stage.run(manifest)
    if manifest.project.final_video:
        print(f"\nFinal video: {manifest.project.final_video}")
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    if not PROJECTS_DIR.exists():
        print("No projects yet.")
        return 0
    for d in sorted(PROJECTS_DIR.iterdir()):
        if (d / "manifest.json").exists():
            print(d.name)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="historygen", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="create a project and generate its script")
    p_new.add_argument("topic", help="documentary topic, e.g. \"Osmanlı'nın kuruluşu\"")
    p_new.add_argument("--language", default="tr", help="script + voice language code (default: tr)")
    p_new.add_argument("--gender", choices=["male", "female"], default="female", help="voice gender")
    p_new.add_argument(
        "--genre", choices=[g.value for g in Genre], default="auto",
        help="video style (default: auto — the model picks the best style for your topic)",
    )
    p_new.add_argument(
        "--orientation", choices=["vertical", "horizontal", "square"], default="vertical",
        help="frame shape: vertical 9:16 (default), horizontal 16:9, or square",
    )
    p_new.add_argument(
        "--minutes", type=float, default=None,
        help="target spoken length in minutes (default: ~0.9 = a <60s Short)",
    )
    p_new.set_defaults(func=_cmd_new)

    p_run = sub.add_parser("run", help="run the pipeline for a project")
    p_run.add_argument("slug")
    p_run.add_argument("--stage", help="run only this stage")
    p_run.add_argument("--force", action="store_true", help="ignore cache; regenerate")
    p_run.add_argument("--gender", choices=["male", "female"], help="voice gender")
    p_run.add_argument("--language", help="voice language code, e.g. tr, en")
    p_run.set_defaults(func=_cmd_run)

    p_status = sub.add_parser("status", help="show a project's state")
    p_status.add_argument("slug")
    p_status.set_defaults(func=_cmd_status)

    p_list = sub.add_parser("list", help="list all projects")
    p_list.set_defaults(func=_cmd_list)

    p_translate = sub.add_parser(
        "translate", help="clone a project into another language, reusing its visuals"
    )
    p_translate.add_argument("slug", help="source project slug")
    p_translate.add_argument("topic", help="new project topic (used for the new slug)")
    p_translate.add_argument(
        "--language", default="English", help="target language (default: English)"
    )
    p_translate.set_defaults(func=_cmd_translate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)
