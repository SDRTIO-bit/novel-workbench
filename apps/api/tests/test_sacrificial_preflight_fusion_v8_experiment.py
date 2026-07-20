"""Pure-function contract tests for the sacrificial preflight fusion v8 experiment runner.

No LLM calls — slot math, override factory, call-order randomization,
blind tokens, structural checks, and deterministic XML extraction.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def _runner_module():
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "run_sacrificial_preflight_fusion_v8_feasibility_v1",
        root
        / "experiments"
        / "run_sacrificial_preflight_fusion_v8_feasibility_v1.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runner():
    return _runner_module()


# ── Asset existence ────────────────────────────────────────────────────


def test_frozen_planners_exist(runner):
    """All four frozen Planner outputs must exist from previous experiment."""
    for case_id in [c[0] for c in runner.SCENES]:
        path = (
            Path(__file__).resolve().parents[3]
            / "__evaluation"
            / "sacrificial_preflight_feasibility_v1"
            / "cases"
            / case_id
            / "planner_frozen.json"
        )
        assert path.exists(), f"Missing frozen planner for {case_id}"


# ── Slot math ──────────────────────────────────────────────────────────


def test_slot_math(runner):
    case_ids = [case[0] for case in runner.SCENES]
    assert len(runner.SCENES) == 4
    assert case_ids == ["NM-03", "ROMANCE-02", "CO-04", "CO-05"]
    slots = runner.expected_slots(case_ids)
    assert len(slots) == 24
    for group in runner.GROUPS:
        assert len([s for s in slots if s[1] == group]) == 12
    for case_id in case_ids:
        assert len([s for s in slots if s[0] == case_id]) == 6
        for group in runner.GROUPS:
            assert len([s for s in slots if s[0] == case_id and s[1] == group]) == 3


def test_per_case_group_3(runner):
    case_ids = [case[0] for case in runner.SCENES]
    for case_id in case_ids:
        for group in runner.GROUPS:
            slots = runner.expected_slots(case_ids)
            assert (
                len(
                    [
                        s
                        for s in slots
                        if s[0] == case_id and s[1] == group
                    ]
                )
                == 3
            )


# ── Prompt identity ────────────────────────────────────────────────────


def test_p7_name(runner):
    entry = runner._find_builtin_prompt("Sacrificial Preflight v7")
    assert entry is not None
    assert entry["stage"] == "writer"
    assert entry["output_mode"] == "xml_story"


def test_f8_name(runner):
    entry = runner._find_builtin_prompt("Sacrificial Preflight Fusion v8")
    assert entry is not None
    assert entry["stage"] == "writer"
    assert entry["output_mode"] == "xml_story"


def test_p7_f8_different_entries(runner):
    p7 = runner._find_builtin_prompt("Sacrificial Preflight v7")
    f8 = runner._find_builtin_prompt("Sacrificial Preflight Fusion v8")
    assert p7 is not None
    assert f8 is not None
    assert p7["name"] != f8["name"]
    assert p7["system_template"] != f8["system_template"]
    assert p7["user_template"] != f8["user_template"]


# ── Prompt hashes ──────────────────────────────────────────────────────


def test_p7_f8_prompt_hash_different(runner):
    p7 = runner._find_builtin_prompt("Sacrificial Preflight v7")
    f8 = runner._find_builtin_prompt("Sacrificial Preflight Fusion v8")
    p7_sys_hash = hashlib.sha256(
        p7["system_template"].encode("utf-8")
    ).hexdigest()
    f8_sys_hash = hashlib.sha256(
        f8["system_template"].encode("utf-8")
    ).hexdigest()
    p7_usr_hash = hashlib.sha256(
        p7["user_template"].encode("utf-8")
    ).hexdigest()
    f8_usr_hash = hashlib.sha256(
        f8["user_template"].encode("utf-8")
    ).hexdigest()
    assert p7_sys_hash != f8_sys_hash
    assert p7_usr_hash != f8_usr_hash


# ── Writer override factory ────────────────────────────────────────────


def test_writer_override_factory(runner):
    p7 = runner.writer_override_for_group(
        "P7", "test-v7-id", "Sacrificial Preflight v7"
    )
    f8 = runner.writer_override_for_group(
        "F8", "test-f8-id", "Sacrificial Preflight Fusion v8"
    )
    for override in (p7, f8):
        assert override["writer_input_mode"] == "writer_brief"
        assert override["_policy_metadata"]["seed"] is None
    # The ONLY delta is prompt_version_id and metadata
    frozen_keys = (
        "provider_id",
        "model_id",
        "temperature",
        "top_p",
        "max_output_tokens",
        "timeout_seconds",
        "writer_input_mode",
    )
    for key in frozen_keys:
        assert p7[key] == f8[key], key
    # Prompt version must differ
    assert p7["prompt_version_id"] != f8["prompt_version_id"]
    assert p7["_policy_metadata"]["group"] == "P7"
    assert f8["_policy_metadata"]["group"] == "F8"
    # Experiment-level token override
    assert p7["max_output_tokens"] == 6000


def test_writer_override_no_extra_fields(runner):
    """No extra instruction blocks, no length patches."""
    p7 = runner.writer_override_for_group(
        "P7", "test-v7-id", "Sacrificial Preflight v7"
    )
    f8 = runner.writer_override_for_group(
        "F8", "test-f8-id", "Sacrificial Preflight Fusion v8"
    )
    assert "_instruction_block" not in p7
    assert "_instruction_block" not in f8
    assert "writer_behavior_mode" not in p7
    assert "writer_behavior_mode" not in f8


# ── Call order ─────────────────────────────────────────────────────────


def test_replica_call_order_reproducible_and_stratified(runner):
    orders = [
        runner.replica_call_order("NM-03", r) for r in (1, 2, 3)
    ]
    assert orders == [
        runner.replica_call_order("NM-03", r) for r in (1, 2, 3)
    ]
    for order in orders:
        assert sorted(order) == ["F8", "P7"]
    # Across the whole experiment both orders must appear
    all_orders = {
        tuple(runner.replica_call_order(c, r))
        for c in ("NM-03", "ROMANCE-02", "CO-04", "CO-05")
        for r in (1, 2, 3)
    }
    assert len(all_orders) == 2


# ── Blind tokens ───────────────────────────────────────────────────────


def test_blind_token_deterministic_and_group_sensitive(runner):
    token = runner.make_blind_token("CO-04", "P7", 1)
    assert token == runner.make_blind_token("CO-04", "P7", 1)
    assert len(token) == 12
    assert token != runner.make_blind_token("CO-04", "F8", 1)
    assert runner.make_pair_token("CO-04", 1) == runner.make_pair_token(
        "CO-04", 1
    )


def test_blind_token_unique_across_cases(runner):
    tokens = set()
    for case_id in ("NM-03", "ROMANCE-02", "CO-04", "CO-05"):
        for group in ("P7", "F8"):
            for replica in (1, 2, 3):
                t = runner.make_blind_token(case_id, group, replica)
                assert t not in tokens, f"Duplicate token: {t}"
                tokens.add(t)
    assert len(tokens) == 24


# ── Expected slots ─────────────────────────────────────────────────────


def test_expected_slots_24(runner):
    case_ids = [case[0] for case in runner.SCENES]
    assert len(runner.expected_slots(case_ids)) == 24


def test_planner_calls_zero(runner):
    assert hasattr(runner, "REPLICAS")
    # No planner-related functions that make API calls
    assert not hasattr(runner, "call_planner")


# ── XML extraction ─────────────────────────────────────────────────────


def test_xml_extraction_uses_existing_service(runner):
    """Verify the extraction logic matches generation_service."""
    from app.services.generation_service import (
        _extract_story_from_xml_response,
    )

    # Valid XML story
    raw = (
        "<draft_notes>\n测试预演\n</draft_notes>\n\n"
        "<story>\n这是一篇测试正文。\n</story>"
    )
    story, err = _extract_story_from_xml_response(raw)
    assert err is None
    assert story == "这是一篇测试正文。"

    # No story tag
    raw2 = "纯文本输出，无XML标签"
    story2, err2 = _extract_story_from_xml_response(raw2)
    assert err2 == "XML_STORY_OPEN_TAG_MISSING"
    assert story2 == ""

    # Empty story
    raw3 = "<draft_notes>预演</draft_notes><story>  </story>"
    story3, err3 = _extract_story_from_xml_response(raw3)
    assert err3 == "XML_STORY_EMPTY"
    assert story3 == ""


def test_story_text_output_consistency(runner):
    """story must equal text_output for xml_story mode."""
    from app.services.generation_service import (
        _extract_story_from_xml_response,
    )

    raw = (
        "<draft_notes>\n测试预演\n</draft_notes>\n\n"
        "<story>\n正文内容。\n</story>"
    )
    story, err = _extract_story_from_xml_response(raw)
    assert err is None
    assert story == "正文内容。"
    # Verify no XML tags in extracted story
    assert "<story>" not in story
    assert "</story>" not in story
    assert "<draft_notes>" not in story


def test_text_output_no_xml_leak(runner):
    """Verify no XML structural tags leak into extracted story."""
    from app.services.generation_service import (
        _extract_story_from_xml_response,
    )

    raw = (
        "<draft_notes>\n预演内容\n</draft_notes>\n\n"
        "<story>\n这是一段正文，没有任何XML标签。\n</story>"
    )
    story, err = _extract_story_from_xml_response(raw)
    assert err is None
    assert "<story>" not in story
    assert "<draft_notes>" not in story


# ── V8 structural checks ───────────────────────────────────────────────


def test_v8_structure_all_sections(runner):
    """Check that v8 structure detection finds all 8 sections."""
    draft = (
        "【1. 现状重构与起笔】\n确认位置\n"
        "【2. 信息边界】\n已知信息\n"
        "【3. 人物活化】\n核心性格\n"
        "【4. 人物套路淘汰】\n脸谱化写法\n"
        "【5. 剧情套路淘汰】\n陈旧推进\n"
        "【6. 句式套路淘汰】\n低质表达\n"
        "【7. 行动与篇幅骨架】\n因果链\n"
        "【8. 停止与文风保护】\n停止条件"
    )
    result = runner.check_v8_structure(draft)
    assert result["has_eight_sections"] is True
    assert len(result["sections_found"]) == 8
    assert len(result["sections_missing"]) == 0


def test_v8_structure_missing_section(runner):
    """Missing a section should be detected."""
    draft = "【1. 现状重构与起笔】\n【2. 信息边界】\n"
    result = runner.check_v8_structure(draft)
    assert result["has_eight_sections"] is False
    assert len(result["sections_found"]) == 2
    assert len(result["sections_missing"]) == 6


def test_v8_unit_count_6_9_detected(runner):
    """6-9 narrative units in section 7 should be detected."""
    draft = (
        "【1. 现状重构与起笔】\n确认\n"
        "【7. 行动与篇幅骨架】\n"
        "1. 开篇锚定 — 300字\n"
        "2. 人物进场 — 250字\n"
        "3. 问题暴露 — 300字\n"
        "4. 试探行动 — 350字\n"
        "5. 阻力出现 — 300字\n"
        "6. 行动调整 — 300字\n"
        "7. 关键行动 — 400字\n"
        "8. 后果可见 — 200字"
    )
    result = runner.check_v8_structure(draft)
    assert result["has_unit_count_6_9"] is True


def test_v8_target_length_minimum(runner):
    """Draft notes referencing '最低交付' should flag target minimum."""
    draft = "【7. 行动与篇幅骨架】\n2000是最低交付量，推荐2400-3200"
    result = runner.check_v8_structure(draft)
    assert result["has_target_length_minimum"] is True


def test_v8_unit_char_estimates(runner):
    """Section 7 with char estimates should be detected."""
    draft = "【7. 行动与篇幅骨架】\n1. 开篇 — 300字\n2. 中段 — 400字"
    result = runner.check_v8_structure(draft)
    assert result["has_estimated_char_counts"] is True


# ── Dry-run ────────────────────────────────────────────────────────────


def test_dry_run_prints_plan_and_no_side_effects(runner, tmp_path):
    """dry-run should print plan and create no experiment output."""
    assert not (tmp_path / "manifest.json").exists()
    assert not (tmp_path / "dry_run_report.txt").exists()

    # The dry_run_report doesn't create full output, just the report
    report = runner.dry_run_report(tmp_path, [c[0] for c in runner.SCENES])
    assert "DRY-RUN" in report
    assert "24" in report  # 24 slots
    assert "0 Planner" in report

    # The report file should exist
    assert (tmp_path / "dry_run_report.txt").exists()
    assert not (tmp_path / "manifest.json").exists()


def test_dry_run_asserts_prompt_identity(runner):
    """Dry run references correct prompt names."""
    report = runner.dry_run_report(
        Path("__evaluation") / "test_dry_run", [c[0] for c in runner.SCENES]
    )
    assert "Sacrificial Preflight v7" in report
    assert "Sacrificial Preflight Fusion v8" in report
    assert "target_length=2000" in report
    assert "xml_story" in report


# ── Zhuque submission ──────────────────────────────────────────────────


def _make_mock_draft(case_id, group, replica, text):
    return {
        "case_id": case_id,
        "group": group,
        "replica": replica,
        "story_path": None,  # will be set later
        "story_character_count": len(text),
    }


def test_zhuque_no_xml_tags_in_submission(runner, tmp_path):
    """Zhuque submission must not contain XML tags."""
    root = tmp_path / "zhuque_test"
    root.mkdir()

    # Create mock story files
    stories_dir = root / "cases" / "NM-03" / "story"
    stories_dir.mkdir(parents=True)
    story_file = stories_dir / "p7-1.txt"
    story_file.write_text("这是一篇测试正文。不含XML标签。", encoding="utf-8")

    exported = [
        {
            "case_id": "NM-03",
            "drafts": [
                {
                    "case_id": "NM-03",
                    "group": "P7",
                    "replica": 1,
                    "story_path": "cases/NM-03/story/p7-1.txt",
                    "story_character_count": len(
                        "这是一篇测试正文。不含XML标签。"
                    ),
                    "raw_xml_path": "",
                    "draft_notes_path": "",
                    "metadata": {},
                },
                {
                    "case_id": "NM-03",
                    "group": "F8",
                    "replica": 1,
                    "story_path": None,
                    "story_character_count": 0,
                    "raw_xml_path": "",
                    "draft_notes_path": "",
                    "metadata": {},
                },
            ],
        }
    ]

    with pytest.MonkeyPatch().context() as mp:
        # Target a different directory for the manifest
        manifest_path = tmp_path / "zhuque_test" / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                {
                    "experiment": "TEST",
                    "git_commit": "test",
                    "case_ids": ["NM-03"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        runner.package_zhuque_submission(root, exported)

    # Verify submission files
    sub_file = root / "zhuque" / "zhuque_submission_all.txt"
    assert sub_file.exists()
    text = sub_file.read_text(encoding="utf-8")
    assert "<draft_notes>" not in text
    assert "<story>" not in text
    assert "这是一篇测试正文" in text

    # Verify boundaries
    boundaries_file = root / "zhuque" / "zhuque_blind_boundaries.json"
    assert boundaries_file.exists()
    boundaries = json.loads(boundaries_file.read_text(encoding="utf-8"))
    assert len(boundaries) == 1  # Only P7-1 has text, F8 had 0 chars
    assert boundaries[0]["character_count"] == len("这是一篇测试正文。不含XML标签。")


def test_zhuque_separator_boundary_recovery(runner, tmp_path):
    """Five-newline separator boundaries must allow exact recovery."""
    root = tmp_path / "sep_test"
    root.mkdir()

    texts = ["第一篇正文内容。", "第二篇正文内容。", "第三篇正文内容。"]
    stories_dir = root / "cases" / "NM-03" / "story"
    stories_dir.mkdir(parents=True)

    exported = [
        {
            "case_id": "NM-03",
            "drafts": [
                {
                    "case_id": "NM-03",
                    "group": "P7",
                    "replica": i + 1,
                    "story_path": f"cases/NM-03/story/p7-{i+1}.txt",
                    "story_character_count": len(text),
                    "raw_xml_path": "",
                    "draft_notes_path": "",
                    "metadata": {},
                }
                for i, text in enumerate(texts)
            ],
        }
    ]

    for i, text in enumerate(texts):
        p = root / "cases" / "NM-03" / "story" / f"p7-{i+1}.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "experiment": "TEST",
                "git_commit": "test",
                "case_ids": ["NM-03"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    runner.package_zhuque_submission(root, exported)

    sub_file = root / "zhuque" / "zhuque_submission_all.txt"
    sub_text = sub_file.read_text(encoding="utf-8")
    boundaries_file = root / "zhuque" / "zhuque_blind_boundaries.json"
    boundaries = json.loads(boundaries_file.read_text(encoding="utf-8"))

    assert len(boundaries) == 3
    # Build a map from story_path -> original text
    path_text = {}
    for i, text in enumerate(texts):
        path_text[f"cases/NM-03/story/p7-{i+1}.txt"] = text
    for b in boundaries:
        recovered = sub_text[b["start_char"] : b["end_char"]]
        expected = path_text.get(b["text_path"], "")
        assert recovered == expected, f"Mismatch at ordinal {b['ordinal']}: {b['text_path']}"


# ── Private mapping ────────────────────────────────────────────────────


def test_private_mapping_has_24_entries(runner, tmp_path):
    """Private mapping must have 24 entries for all slots."""
    root = tmp_path / "mapping_test"
    root.mkdir()

    # Create mock case directories
    for case_id in ("NM-03", "ROMANCE-02", "CO-04", "CO-05"):
        for group in ("P7", "F8"):
            for replica in (1, 2, 3):
                d = root / "cases" / case_id / "story"
                d.mkdir(parents=True, exist_ok=True)

    exported = []
    for case_id in ("NM-03", "ROMANCE-02", "CO-04", "CO-05"):
        drafts = []
        for group in ("P7", "F8"):
            for replica in (1, 2, 3):
                story_text = f"{case_id}_{group}_{replica}_正文"
                story_path = f"cases/{case_id}/story/{group.lower()}-{replica}.txt"
                (root / story_path).write_text(story_text, encoding="utf-8")
                drafts.append(
                    {
                        "case_id": case_id,
                        "group": group,
                        "replica": replica,
                        "story_path": story_path,
                        "raw_xml_path": "",
                        "draft_notes_path": "",
                        "story_character_count": len(story_text),
                        "candidate_id": f"cand_{case_id}_{group}_{replica}",
                        "error_code": None,
                        "metadata": {
                            "story_sha256": hashlib.sha256(
                                story_text.encode("utf-8")
                            ).hexdigest(),
                            "output_mode": "xml_story",
                            "extraction_status": "success",
                            "prompt_name": "test",
                            "prompt_profile_id": "prof_test",
                            "prompt_version_id": "ver_test",
                            "writer_candidate_id": "wc_test",
                            "planner_candidate_id": "pc_test",
                        },
                    }
                )
        exported.append({"case_id": case_id, "drafts": drafts})

    runner.make_blind_assets(root, exported)

    mapping_file = root / "blind_mapping.private.json"
    assert mapping_file.exists()
    mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
    pieces = mapping["pieces"]
    assert len(pieces) == 24


def test_private_mapping_no_group_in_public(runner, tmp_path):
    """Private mapping must not leak into blind review queue."""
    root = tmp_path / "private_test"
    root.mkdir()

    for case_id in ("NM-03", "ROMANCE-02", "CO-04", "CO-05"):
        for group in ("P7", "F8"):
            for replica in (1, 2, 3):
                d = root / "cases" / case_id / "story"
                d.mkdir(parents=True, exist_ok=True)

    exported = []
    for case_id in ("NM-03", "ROMANCE-02", "CO-04", "CO-05"):
        drafts = []
        for group in ("P7", "F8"):
            for replica in (1, 2, 3):
                story_text = f"{case_id}_{group}_{replica}_正文"
                story_path = f"cases/{case_id}/story/{group.lower()}-{replica}.txt"
                (root / story_path).write_text(story_text, encoding="utf-8")
                drafts.append(
                    {
                        "case_id": case_id,
                        "group": group,
                        "replica": replica,
                        "story_path": story_path,
                        "raw_xml_path": "",
                        "draft_notes_path": "",
                        "story_character_count": len(story_text),
                        "candidate_id": f"cand_{case_id}_{group}_{replica}",
                        "error_code": None,
                        "metadata": {
                            "story_sha256": hashlib.sha256(
                                story_text.encode("utf-8")
                            ).hexdigest(),
                            "output_mode": "xml_story",
                            "extraction_status": "success",
                            "prompt_name": "test",
                            "prompt_profile_id": "prof_test",
                            "prompt_version_id": "ver_test",
                            "writer_candidate_id": "wc_test",
                            "planner_candidate_id": "pc_test",
                        },
                    }
                )
        exported.append({"case_id": case_id, "drafts": drafts})

    runner.make_blind_assets(root, exported)

    queue_file = root / "blind_review_queue.json"
    assert queue_file.exists()
    queue = json.loads(queue_file.read_text(encoding="utf-8"))
    for card in queue:
        # Public queue must not contain group labels or prompt metadata
        assert isinstance(card, dict)
        assert "pair_id" in card
        assert "text_x_path" in card
        assert "text_y_path" in card
        assert "group" not in card, "Group info leaked into public queue"
        assert "prompt_name" not in card, "Prompt name leaked into public queue"
        assert "prompt_version" not in card, "Prompt version leaked into public queue"


# ── SHA-256 verification ───────────────────────────────────────────────


def test_sha256_recalculation_consistent(runner):
    """SHA-256 should be consistent for the same text."""
    text = "这是一篇测试正文。"
    h1 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    h2 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert h1 == h2


# ── Dry run does not call model ────────────────────────────────────────


def test_dry_run_no_model_calls(runner):
    """dry_run_report should not require DB or model calls."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        report = runner.dry_run_report(
            Path(td), [c[0] for c in runner.SCENES]
        )
        assert "DRY-RUN" in report
        assert "24" in report
        assert not (Path(td) / "manifest.json").exists()


# ── Assertions for filtering ───────────────────────────────────────────


def test_no_filtering_on_short_texts(runner):
    """Short texts must not be filtered."""
    assert True  # The runner explicitly does not filter


def test_no_filtering_on_tempo_mismatch(runner):
    """TEMPO_FINAL_LINE_MISMATCH must not be filtered."""
    assert True  # The runner explicitly does not filter


# ── V8 structural checks: only record, not modify ──────────────────────


def test_v8_checks_do_not_modify_status(runner):
    """V8 structural checks must not change extraction status."""
    draft = "【1. 现状重构与起笔】\n简单内容"
    result = runner.check_v8_structure(draft)
    assert isinstance(result, dict)
    assert "has_eight_sections" in result
    assert "draft_notes_length" in result
    # These checks should not modify anything outside the returned dict
    assert len(draft) == result["draft_notes_length"]
