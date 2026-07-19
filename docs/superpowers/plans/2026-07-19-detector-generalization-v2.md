# DETECTOR_GENERALIZATION_V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a controlled 72-draft experiment in which only C receives a compact novel-writing behaviour instruction in addition to its four-field Brief.

**Architecture:** Keep V1 reproducible by making behaviour guidance an explicit Writer-stage override rather than changing the meaning of narrative_behaviour_brief globally. GenerationService appends the guidance only when that override is exact; a V2 runner reuses V1's case and generation machinery while naming its outputs separately and setting the override only for C.

**Tech Stack:** Python 3, FastAPI service layer, Pydantic, SQLAlchemy async, pytest, DeepSeek OpenAI-compatible provider.

## Global Constraints

- A and B retain their existing Writer instruction and input payloads.
- C differs from B by only available_causal_objects, rejected_alternative, cost_or_commitment, and counteraction_or_disproof, plus its short Writer behaviour instruction.
- Use deepseek-v4-pro with thinking={"type":"disabled"} and 4,000 Writer output tokens.
- Generate 12 fixed scenarios × 3 groups × 2 replicas = 72 drafts, with one Planner call per scenario.
- Do not place detector names, scores, labels, or evasion instructions in any prompt.
- Do not invoke Critic, Reviser, Judge, TGbreak, retry, or candidate selection during the experiment.

---

### Task 1: Specify and test the C-only Writer behaviour envelope

**Files:**

- Modify: apps/api/tests/test_writer_brief.py
- Modify: apps/api/app/services/generation_service.py:690-706

**Interfaces:**

- Consumes: GenerationService._append_writer_brief(stage, writer_prompt_mode, ctx, writer_behavior_mode=None).
- Produces: a rendered_user_prompt that contains a stable C-only instruction when writer_behavior_mode == "narrative_behaviour_v1".

- [ ] **Step 1: Write the failing test**

    def test_narrative_behaviour_instruction_is_c_only_and_hashes_into_the_input():
        from app.services.generation_service import GenerationService

        context = {
            "variables": {"writer_brief": '{"next_action":"递出点名册"}'},
            "rendered_user_prompt": "写作指令\n",
            "input_snapshot_hash": "snapshot",
        }
        GenerationService._append_writer_brief(
            "writer", "builtin", context, "narrative_behaviour_v1"
        )

        assert "把关键选择落实为人物对现场可见物件、位置或身体动作的处理" in context["rendered_user_prompt"]
        assert "AI" not in context["rendered_user_prompt"]
        assert "检测" not in context["rendered_user_prompt"]
        assert context["input_snapshot_hash"] != "snapshot"

Add a companion invocation using None and assert that the behaviour sentence is absent.

- [ ] **Step 2: Run test to verify it fails**

Run: python -m pytest -q tests/test_writer_brief.py -k narrative_behaviour_instruction

Expected: FAIL because _append_writer_brief does not accept the fourth argument.

- [ ] **Step 3: Write the minimal implementation**

Add a module constant and extend the helper signature:

    NARRATIVE_BEHAVIOUR_V1 = (
        "\n\n## 场景行动落地\n"
        "把关键选择落实为人物对现场可见物件、位置或身体动作的处理；"
        "让本可采用的另一条做法在行动中被放弃，不用解释性独白交代；"
        "让承诺或代价体现为时间、空间、资源或关系状态的具体变化；"
        "让关键行动引出他人可观察的反应或反制；"
        "在一个新发生、可验证的事实处结束。不得推翻已给出的事实边界。"
    )

    @staticmethod
    def _append_writer_brief(stage, writer_prompt_mode, ctx, writer_behavior_mode=None):
        # Retain the existing builtin/brief guards and base instruction.
        addition = NARRATIVE_BEHAVIOUR_V1 if writer_behavior_mode == "narrative_behaviour_v1" else ""
        ctx["rendered_user_prompt"] += base_writer_brief_text + addition
        ctx["input_snapshot_hash"] = sha256(
            (ctx["input_snapshot_hash"] + brief + addition).encode("utf-8")
        ).hexdigest()

At the existing execute_stage call site, pass override.get("writer_behavior_mode") only for the Writer stage.

- [ ] **Step 4: Run tests to verify they pass**

Run: python -m pytest -q tests/test_writer_brief.py

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

    git add apps/api/app/services/generation_service.py apps/api/tests/test_writer_brief.py
    git commit -m "feat: add c-group narrative behaviour guidance"

### Task 2: Add a separately named V2 experiment runner

**Files:**

- Modify: experiments/run_detector_generalization_v1.py:158-252
- Create: experiments/run_detector_generalization_v2.py
- Modify: apps/api/tests/test_detector_generalization.py

**Interfaces:**

- Consumes: run(root, database, dry_run, case_start, *, experiment=EXPERIMENT, writer_behavior_mode=None).
- Produces: V2 manifests with experiment == "DETECTOR_GENERALIZATION_V2"; C writer overrides include writer_behavior_mode == "narrative_behaviour_v1"; A/B do not.

- [ ] **Step 1: Write the failing runner-contract tests**

    def test_v2_routes_behaviour_guidance_to_c_only():
        runner = _runner_module()

        assert "writer_behavior_mode" not in runner.writer_override_for_group("A", "complete_planner")
        assert "writer_behavior_mode" not in runner.writer_override_for_group("B", "writer_brief")
        assert runner.writer_override_for_group(
            "C", "narrative_behaviour_brief", "narrative_behaviour_v1"
        )["writer_behavior_mode"] == "narrative_behaviour_v1"

Also load experiments/run_detector_generalization_v2.py and assert EXPERIMENT == "DETECTOR_GENERALIZATION_V2" and its default output root contains detector_generalization_v2.

- [ ] **Step 2: Run test to verify it fails**

Run: python -m pytest -q tests/test_detector_generalization.py -k v2

Expected: FAIL because the factory and V2 module do not exist.

- [ ] **Step 3: Refactor V1 without changing its defaults**

Extract its inline writer override into:

    def writer_override_for_group(group, input_mode, writer_behavior_mode=None):
        override = {
            "provider_id": FROZEN["provider_id"],
            "model_id": FROZEN["model_id"],
            "prompt_version_id": FROZEN["writer_prompt_version_id"],
            "temperature": FROZEN["temperature"],
            "top_p": FROZEN["top_p"],
            "max_output_tokens": FROZEN["max_output_tokens"],
            "timeout_seconds": FROZEN["timeout_seconds"],
            "writer_input_mode": input_mode,
        }
        if group == "C" and writer_behavior_mode:
            override["writer_behavior_mode"] = writer_behavior_mode
        return override

Give run keyword-only experiment and writer_behavior_mode parameters with V1-preserving defaults. Use experiment in the manifest, summary and result-template heading; record the behaviour mode in the manifest rules. Replace the inline writer dictionary with the factory.

- [ ] **Step 4: Create the V2 wrapper**

Create experiments/run_detector_generalization_v2.py that imports V1's constants and run, exposes EXPERIMENT = "DETECTOR_GENERALIZATION_V2", accepts --root, --database, --dry-run, --case-start, and --model-id, sets the requested model and Planner cap exactly as V1 does, then calls:

    asyncio.run(run(
        args.root, args.database, args.dry_run, args.case_start,
        experiment=EXPERIMENT,
        writer_behavior_mode="narrative_behaviour_v1",
    ))

Its defaults must be __evaluation/detector_generalization_v2 and __evaluation/detector_generalization_v2.sqlite3.

- [ ] **Step 5: Run focused and API tests**

Run: python -m pytest -q tests/test_detector_generalization.py tests/test_writer_brief.py tests/test_structured_transport.py

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

    git add experiments/run_detector_generalization_v1.py experiments/run_detector_generalization_v2.py apps/api/tests/test_detector_generalization.py
    git commit -m "feat: add detector generalization v2 runner"

### Task 3: Run and package the controlled V2 batch

**Files:**

- Create: __evaluation/detector_generalization_v2/ (generated evidence and drafts)
- Create: __evaluation/detector_generalization_v2_final/zhuque_submission_all.txt
- Create: __evaluation/detector_generalization_v2_final/source_mapping.private.json
- Create: __evaluation/detector_generalization_v2_final/blind_review_queue.json
- Create: __evaluation/detector_generalization_v2_final/manifest.json

**Interfaces:**

- Consumes: the V2 runner, valid configured DeepSeek provider, and all 12 CASE_SPECS.
- Produces: 72 completed text drafts, an anonymous UTF-8 TXT, and a private blind-ID-to-source mapping.

- [ ] **Step 1: Smoke-check V2 configuration without model calls**

Run: python ../../experiments/run_detector_generalization_v2.py --dry-run --model-id deepseek-v4-pro --root ../../__evaluation/detector_generalization_v2_smoke --database ../../__evaluation/detector_generalization_v2_smoke.sqlite3

Expected: manifest declares V2, deepseek-v4-pro, 4,000 Writer tokens, two replicas, and C-only narrative_behaviour_v1; no Writer drafts are requested.

- [ ] **Step 2: Execute the full batch**

Run: python ../../experiments/run_detector_generalization_v2.py --model-id deepseek-v4-pro --root ../../__evaluation/detector_generalization_v2 --database ../../__evaluation/detector_generalization_v2.sqlite3

Expected: one Planner result for each of 12 cases and 72 Writer drafts; V4 Pro requests include thinking: {"type":"disabled"}; no downstream generation stages are present.

- [ ] **Step 3: Verify completeness, model invariants, and boundaries**

Run:

    python -c "import json, pathlib; r=pathlib.Path('__evaluation/detector_generalization_v2'); s=json.loads((r/'execution_summary.json').read_text(encoding='utf-8')); assert s['writer_drafts_completed']==72, s; assert s['writer_drafts_expected']==72, s; print(s)"

Inspect all 12 result.json files to confirm exactly two drafts for each A/B/C, only C has the behaviour mode in its input evidence, and no candidate has an unexpected external-fact error.

- [ ] **Step 4: Build a manual-review package**

Use the existing blind-queue exporter to create a shuffled, group-free zhuque_submission_all.txt; retain source paths and group mappings only in source_mapping.private.json. Add a blank detector-results template that explicitly warns that external segmentation may cross sample boundaries.

- [ ] **Step 5: Run final tests and commit stable evidence**

Run: python -m pytest -q from apps/api.

Expected: PASS (record warnings separately).

Commit source, tests, runner, manifests, anonymous text, and mapping; do not add copied SQLite databases, journals, runtime logs, smoke output, .tmp, .omo, or incomplete historical runs.

    git add apps/api/app/services/generation_service.py apps/api/tests/test_writer_brief.py apps/api/tests/test_detector_generalization.py experiments/run_detector_generalization_v1.py experiments/run_detector_generalization_v2.py __evaluation/detector_generalization_v2 __evaluation/detector_generalization_v2_final
    git commit -m "test: run detector generalization v2"

## Self-review

- Spec coverage: Task 1 supplies the C-only fiction technique without expanding Planner; Task 2 freezes A/B and gives V2 an auditable identity; Task 3 executes exactly 72 drafts with the specified V4 Pro configuration and packages the blind manual submission.
- Placeholder scan: no TBD/TODO instructions remain.
- Type consistency: writer_behavior_mode is the same optional string in GenerationService, the override factory, V2 runner and tests; the only accepted V2 value is narrative_behaviour_v1.

