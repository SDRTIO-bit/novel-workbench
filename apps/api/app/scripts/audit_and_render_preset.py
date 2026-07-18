import argparse
import json
import sys
from pathlib import Path

from app.tgbreak.importer import SillyTavernImportError, import_sillytavern_preset
from app.tgbreak.profile import build_tgbreak_core_profile
from app.tgbreak.renderer import TgbreakRenderError, adapt_project_variables, render_tgbreak


def _audit_expected_sha(cwd: Path, preset_path: Path) -> str | None:
    for base in (cwd, cwd.parent, cwd.parent.parent):
        audit_path = base / ".local" / "audits" / "tgbreak-v3.0.5-source-audit.json"
        if not audit_path.exists():
            continue
        data = json.loads(audit_path.read_text(encoding="utf-8"))
        audited_path = Path(data.get("source_path", "")).resolve()
        if audited_path == preset_path.resolve():
            return data.get("sha256")
    return None


def run_dry_run(preset_path: str | Path, profile_name: str, cwd: Path | None = None) -> int:
    cwd = cwd or Path.cwd()
    preset_path = Path(preset_path).expanduser()
    try:
        preset = import_sillytavern_preset(preset_path)
        expected_sha = _audit_expected_sha(cwd, preset_path)
        if expected_sha and expected_sha != preset.source_sha256:
            raise ValueError(
                f"SOURCE_SHA_MISMATCH: expected {expected_sha}, got {preset.source_sha256}"
            )
        if profile_name != "tgbreak-core":
            raise ValueError(f"PROFILE_NOT_SUPPORTED: {profile_name}")
        profile = build_tgbreak_core_profile(preset)
        rendered = render_tgbreak(
            preset,
            profile,
            adapt_project_variables(
                project_documents="dry-run project documents",
                session_summary="dry-run session summary",
                recent_chapters="dry-run recent chapters",
                current_chapter_text="dry-run current chapter",
                scene_instruction="dry-run user request",
                user="dry-run user",
                char="dry-run character",
            ),
            chat_history="dry-run chat history",
            user_message="dry-run user request",
        )
    except (SillyTavernImportError, TgbreakRenderError, ValueError, OSError) as exc:
        print(f"REAL_TGBREAK_DRY_RUN_FAILED: {exc}")
        return 1

    system_count = sum(message.role == "system" for message in rendered.messages)
    assistant_count = sum(message.role == "assistant" for message in rendered.messages)
    print("REAL_TGBREAK_DRY_RUN_OK")
    print(f"source prompt count={len(preset.entries)}")
    print(f"enabled prompt count={sum(entry.enabled for entry in preset.entries)}")
    print(f"rendered message count={len(rendered.messages)}")
    print(f"system message count={system_count}")
    print(f"assistant message count={assistant_count}")
    print(f"unresolved macro count={len(rendered.unresolved_macros)}")
    print(f"draft_notes requirement detected={str(rendered.draft_notes_required).lower()}")
    print(f"source sha256={preset.source_sha256}")
    print(f"resolved entry count={len(rendered.resolved_entry_identifiers)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit and render a local TGbreak preset without a model call")
    parser.add_argument("--preset", required=True)
    parser.add_argument("--profile", default="tgbreak-core")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run:
        parser.error("--dry-run is required; this command never calls a model")
    return run_dry_run(args.preset, args.profile)


if __name__ == "__main__":
    sys.exit(main())
