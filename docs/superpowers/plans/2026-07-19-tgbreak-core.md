# TGbreak Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the smallest source-evidenced TGbreak preset importer, Core profile, macro renderer, ordered message assembler, draft-notes parser, database persistence, tests, and real-file dry-run.

**Architecture:** Add a focused `app.tgbreak` package with dataclass interfaces. Keep the existing prompt workflow unchanged; expose the new path through a small service/CLI boundary and add database tables for private imported data only. Use the real source SHA and identifiers from `.local/audits`, never prompt names as durable keys.

**Tech Stack:** Python 3.11+, dataclasses, stdlib JSON/regex/hashlib, SQLAlchemy async models, Alembic, pytest.

## Global Constraints

- The real source file is local read-only input; never copy its content into migration, source code, fixtures, snapshots, or Git.
- Source SHA-256 is `f7aa69ee58503b9b38994fedb532d9cb3794b775fb9ad732ecdc7a69a7c2fa10`.
- The source contains 107 prompts, 57 enabled prompts, 4 assistant entries, 8 markers, 28 setvar entries, and 6 getvar entries after in-memory container repair.
- Default Core overrides use real identifiers only; duplicate real anti-omniscience identifiers are both retained.
- Provider-native reasoning is disabled while `<draft_notes>` remains part of the TGbreak contract.
- Unit tests use synthetic fixtures; real validation is only `python -m app.scripts.audit_and_render_preset ... --dry-run`.

### Task 1: TDD core dataclasses and importer

**Files:**
- Create: `apps/api/app/tgbreak/__init__.py`
- Create: `apps/api/app/tgbreak/models.py`
- Create: `apps/api/app/tgbreak/importer.py`
- Test: `apps/api/tests/test_tgbreak_importer.py`

**Interfaces:** `import_sillytavern_preset(source_path: str | Path) -> ImportedPreset`; `ImportedPreset.metadata`, `.entries`, `.source_sha256`; `SillyTavernImportError`.

- [ ] Write tests for prompts order, identifiers, roles, SHA, malformed-EOF in-memory repair, supported fields, and source immutability.
- [ ] Run the focused tests and observe failure because the importer does not exist.
- [ ] Implement strict file read, SHA, standard parse, explicit terminal-container repair, prompt normalization, and unsupported-field reporting.
- [ ] Run focused tests and refactor only after green.

### Task 2: TDD Core profile and renderer

**Files:**
- Create: `apps/api/app/tgbreak/profile.py`
- Create: `apps/api/app/tgbreak/renderer.py`
- Test: `apps/api/tests/test_tgbreak_renderer.py`

**Interfaces:** `build_tgbreak_core_profile(preset) -> CoreProfile`; `render_tgbreak(preset, profile, variables, chat_history=...) -> RenderedPreset`.

- [ ] Write synthetic-fixture tests for setvar/getvar, comment removal, unresolved macro failure, profile overrides, source order, marker insertion, and assistant tail placement.
- [ ] Run the tests red.
- [ ] Implement identifier-based overrides, variable interpolation only at the outer data layer, independent messages, debug trace, and unresolved-macro errors.
- [ ] Run focused tests green.

### Task 3: TDD output parser and request metadata

**Files:**
- Create: `apps/api/app/tgbreak/output.py`
- Modify: `apps/api/app/llm/base.py`
- Test: `apps/api/tests/test_tgbreak_output.py`

**Interfaces:** `parse_tgbreak_response(raw_response, ...) -> TgbreakOutput`; `LlmRequest.reasoning_mode` defaults to `disabled`.

- [ ] Write tests for closed tags, missing closing tag failure, draft text extraction, extra module preservation, and reasoning metadata.
- [ ] Run red, implement deterministic extraction without model repair, then run green.

### Task 4: Persistence and dry-run command

**Files:**
- Create: `apps/api/app/models/tgbreak.py`
- Create: `apps/api/alembic/versions/<new>_add_tgbreak_imports.py`
- Create: `apps/api/app/scripts/audit_and_render_preset.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/alembic/env.py`
- Test: `apps/api/tests/test_tgbreak_persistence.py`

**Interfaces:** private preset/entry/profile rows preserve imported content and identifier overrides; the command prints `REAL_TGBREAK_DRY_RUN_OK` and the required counters.

- [ ] Write tests that create/delete imported rows without touching the source file and verify the old prompt workflow still passes.
- [ ] Run red.
- [ ] Implement tables, migration, model registration, and the no-model dry-run command using temporary in-memory data.
- [ ] Run focused and existing prompt tests green.

### Task 5: Source evidence and full verification

**Files:**
- Modify: `.local/audits/tgbreak-v3.0.5-source-audit.json`
- Modify: `.local/audits/tgbreak-v3.0.5-variable-graph.json`
- Test: `apps/api/tests/test_tgbreak_real_safety.py`

- [ ] Add a local-only safety test/command path that checks source SHA, Git ignore, and absence of source path/content in tracked files.
- [ ] Run the full API test suite.
- [ ] Run the real dry-run against the Downloads source path with no model client.
- [ ] Run `git check-ignore -v` and `git status --short`, review the diff, commit only intended tracked files, and report the commit SHA.
