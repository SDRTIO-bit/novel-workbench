import json

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tgbreak import (
    SillyTavernPreset,
    SillyTavernPromptEntry,
    TgbreakOutputRecord,
    TgbreakProfile,
)
from app.tgbreak.models import CoreProfile, ImportedPreset, TgbreakOutput


async def persist_imported_preset(session: AsyncSession, imported: ImportedPreset) -> SillyTavernPreset:
    existing = await session.scalar(
        select(SillyTavernPreset)
        .where(SillyTavernPreset.source_sha256 == imported.source_sha256)
        .options(selectinload(SillyTavernPreset.entries))
    )
    if existing:
        return existing

    row = SillyTavernPreset(
        id=imported.preset_id,
        source_path=imported.metadata.source_path,
        source_sha256=imported.source_sha256,
        file_size=imported.metadata.file_size,
        source_format_version=imported.metadata.source_format_version,
        top_level_keys_json=json.dumps(imported.metadata.top_level_keys, ensure_ascii=False),
        unsupported_fields_json=json.dumps(imported.metadata.unsupported_fields, ensure_ascii=False),
        parse_mode=imported.metadata.parse_mode,
        standard_json_parse_error_json=(
            json.dumps(imported.metadata.standard_json_parse_error, ensure_ascii=False)
            if imported.metadata.standard_json_parse_error else None
        ),
    )
    session.add(row)
    await session.flush()
    for entry in imported.entries:
        session.add(SillyTavernPromptEntry(
            preset_id=row.id,
            array_index=entry.array_index,
            identifier=entry.identifier,
            name=entry.name,
            enabled=entry.enabled,
            role=entry.role,
            content=entry.content,
            system_prompt=entry.system_prompt,
            marker=entry.marker,
            injection_position=entry.injection_position,
            injection_depth=entry.injection_depth,
            injection_order=entry.injection_order,
            injection_trigger_json=json.dumps(entry.injection_trigger, ensure_ascii=False),
            forbid_overrides=entry.forbid_overrides,
        ))
    await session.flush()
    return row


async def persist_core_profile(session: AsyncSession, profile: CoreProfile) -> TgbreakProfile:
    row = TgbreakProfile(
        source_preset_id=profile.source_preset_id,
        source_sha256=profile.source_sha256,
        entry_overrides_json=json.dumps(profile.entry_overrides, ensure_ascii=False),
    )
    session.add(row)
    await session.flush()
    return row


async def delete_imported_preset(session: AsyncSession, preset_id: str) -> None:
    row = await session.scalar(
        select(SillyTavernPreset)
        .where(SillyTavernPreset.id == preset_id)
        .options(selectinload(SillyTavernPreset.entries), selectinload(SillyTavernPreset.profiles))
    )
    if row:
        await session.delete(row)
        await session.flush()


async def persist_tgbreak_output(
    session: AsyncSession,
    candidate_id: str,
    output: TgbreakOutput,
) -> TgbreakOutputRecord:
    row = TgbreakOutputRecord(
        candidate_id=candidate_id,
        raw_response=output.raw_response,
        draft_notes=output.draft_notes,
        draft_text=output.draft_text,
        extra_modules_json=json.dumps(output.extra_modules, ensure_ascii=False),
        source_preset_id=output.source_preset_id,
        source_preset_sha256=output.source_preset_sha256,
        resolved_entry_identifiers_json=json.dumps(
            output.resolved_entry_identifiers, ensure_ascii=False
        ),
        requested_reasoning_mode=output.requested_reasoning_mode,
        reasoning_tokens=output.reasoning_tokens,
    )
    session.add(row)
    await session.flush()
    return row
