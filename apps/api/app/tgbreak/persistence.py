from app.tgbreak.models import TgbreakOutput


def tgbreak_output_record_values(output: TgbreakOutput) -> dict:
    """Return values for the separate TGbreak output record table."""
    return {
        "raw_response": output.raw_response,
        "draft_notes": output.draft_notes,
        "draft_text": output.draft_text,
        "extra_modules": output.extra_modules,
        "source_preset_id": output.source_preset_id,
        "source_preset_sha256": output.source_preset_sha256,
        "resolved_entry_identifiers": output.resolved_entry_identifiers,
        "requested_reasoning_mode": output.requested_reasoning_mode,
        "reasoning_tokens": output.reasoning_tokens,
    }
