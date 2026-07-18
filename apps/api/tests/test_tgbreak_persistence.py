import json

import pytest


def _fixture_path(tmp_path):
    path = tmp_path / "preset.json"
    path.write_text(json.dumps({
        "prompts": [{
            "identifier": "entry",
            "name": "Entry",
            "enabled": True,
            "role": "system",
            "content": "body",
        }],
    }), encoding="utf-8")
    return path


def test_tgbreak_output_storage_does_not_extend_legacy_generation_candidate_table():
    from app.models.generation import GenerationCandidate
    from app.models.tgbreak import TgbreakOutputRecord

    assert "requested_reasoning_mode" not in GenerationCandidate.__table__.columns
    assert "tgbreak_draft_notes" not in GenerationCandidate.__table__.columns
    assert "raw_response" in TgbreakOutputRecord.__table__.columns


@pytest.mark.asyncio
async def test_private_import_and_profile_rows_can_be_deleted_without_source_mutation(tmp_path):
    import app.models.project  # noqa: F401
    import app.models.chapter  # noqa: F401
    import app.models.prompt  # noqa: F401
    import app.models.provider  # noqa: F401
    import app.models.workflow  # noqa: F401
    import app.models.generation  # noqa: F401
    import app.models.tgbreak  # noqa: F401
    from app.db import Base
    from app.services.tgbreak_service import (
        delete_imported_preset,
        persist_core_profile,
        persist_imported_preset,
    )
    from app.tgbreak.importer import import_sillytavern_preset
    from app.tgbreak.models import CoreProfile
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    source = _fixture_path(tmp_path)
    before = source.read_bytes()
    imported = import_sillytavern_preset(source)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        row = await persist_imported_preset(session, imported)
        profile = await persist_core_profile(
            session,
            CoreProfile(imported.preset_id, imported.source_sha256, {"entry": {"enabled": True}}),
        )
        await session.commit()
        assert row.id == imported.preset_id
        assert profile.source_preset_id == imported.preset_id

        await delete_imported_preset(session, imported.preset_id)
        await session.commit()

    assert source.read_bytes() == before
    await engine.dispose()
