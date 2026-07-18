import pytest

from app.llm.output_contracts import (
    validate_tempo_final_line,
    validate_critic_output,
    validate_judge_output_for_selected_issues,
    validate_planner_output,
    validate_reviser_output,
)


def _transition():
    return {
        "id": "CT01",
        "kind": "evidence_to_action",
        "visible_trigger": "\u63a5\u7ebf\u76d2\u91cc\u51fa\u73b0GR-0713",
        "character_interpretation": "\u9646\u8861\u8ba4\u4e3a\u7f16\u53f7\u4e0e\u8bb8\u660e\u8fdc\u6709\u5173",
        "character_next_action": "\u9646\u8861\u8be2\u95ee\u8bb8\u6800\u7236\u4eb2\u7684\u540d\u5b57",
        "rejected_alternative": "\u7ee7\u7eed\u6309\u539f\u5de5\u5355\u6d41\u7a0b\u5904\u7406",
        "reader_must_infer": "\u7f16\u53f7\u4e0e\u8bb8\u660e\u8fdc\u6709\u5173",
        "narrator_must_not_state": ["\u4e24\u4e2a\u7f16\u53f7\u4e00\u81f4"],
        "immediate_consequence": "\u9646\u8861\u6539\u53d8\u8c03\u67e5\u65b9\u5411",
        "counterfactual_without_action": "\u5982\u679c\u9646\u8861\u4e0d\u6539\u53d8\u65b9\u5411\uff0c\u8c03\u67e5\u4f1a\u6309\u539f\u5de5\u5355\u7ed3\u6848",
        "consequence_would_still_happen": False,
        "state_delta": {"before": "\u6309\u539f\u5de5\u5355\u6d41\u7a0b\u5904\u7406", "after": "\u8c03\u67e5\u65b9\u5411\u8f6c\u5411\u8bb8\u660e\u8fdc"},
        "cost_or_commitment": "\u9646\u8861\u504f\u79bb\u4e86\u6807\u51c6\u6d41\u7a0b\uff0c\u627f\u62c5\u8ffd\u67e5\u98ce\u9669",
        "next_constraint": "\u4ed6\u4e0d\u80fd\u900f\u9732\u672a\u6765\u5de5\u5355",
    }


def _tempo_guardrails():
    return {
        "entry_pressure": "\u6797\u9685\u6b63\u628a\u7184\u706b\u7684\u63a2\u6d4b\u8f66\u62d6\u56de\u4ed3\u5e93\u3002",
        "dominant_pressure": {"kind": "physical_problem", "description": "\u51b7\u5374\u7ba1\u91cc\u4f20\u51fa\u6572\u51fb\u58f0"},
        "allowed_viewpoint_misread": "\u4ed6\u4ee5\u4e3a\u538b\u529b\u9600\u677e\u4e86\u3002",
        "disclosure_cap": 1,
        "must_remain_unclassified": ["\u6572\u51fb\u58f0\u6765\u6e90"],
        "stop_state": {
            "type": "physical_change",
            "visible_fact": "\u4ed6\u5207\u65ad\u5916\u95e8\u7535\u6e90",
            "what_is_now_different": "\u4ed3\u5e93\u4e0e\u5916\u90e8\u5b8c\u5168\u65ad\u7535\u9694\u79bb",
            "must_not_append": "\u4e0d\u5f97\u8ffd\u52a0\u5bf9\u6572\u51fb\u58f0\u6765\u6e90\u7684\u89e3\u91ca",
        },
    }


def _all_contract_check_true():
    return {
        "function_aligned": True,
        "must_deliver_covered": True,
        "must_not_deliver_respected": True,
        "main_change_enabled": True,
        "main_payoff_prepared": True,
        "ending_hook_established": True,
        "causal_transitions_grounded": True,
        "reader_inference_not_pre_resolved": True,
        "scene_state_reconstructed": True,
        "information_sources_legal": True,
        "character_choice_is_real": True,
        "consequence_is_counterfactual": True,
        "state_delta_is_nonempty": True,
        "next_constraint_is_new": True,
        "stop_state_is_visible": True,
        "stop_state_changes_future_actions": True,
    }


def _planner_data_v1():
    return {
        "planner_contract_version": 1,
        "scene_goal": "\u63a8\u8fdb\u5f02\u5e38", "location": "\u673a\u5e93", "time": "\u6362\u73ed\u524d",
        "characters": [], "pressure": "\u5373\u5c06\u4ea4\u73ed", "turning_point": "\u6572\u51fb\u58f0\u518d\u6b21\u51fa\u73b0",
        "end_condition": "\u5207\u65ad\u7535\u6e90", "forbidden": [],
        "causal_transitions": [], "chapter_contract_check": {},
    }


def _planner_data_v2():
    return {
        "planner_contract_version": 2,
        "scene_goal": "\u63a8\u8fdb\u5f02\u5e38", "location": "\u673a\u5e93", "time": "\u6362\u73ed\u524d",
        "scene_state": {
            "present_characters": ["\u6797\u9685"],
            "visible_facts": ["\u63a2\u6d4b\u8f66\u7184\u706b"],
        },
        "concrete_problem": "\u6572\u51fb\u58f0\u6765\u6e90\u662f\u4ec0\u4e48",
        "characters": [], "pressure": "\u5373\u5c06\u4ea4\u73ed", "turning_point": "\u6572\u51fb\u58f0\u518d\u6b21\u51fa\u73b0",
        "end_condition": "\u5207\u65ad\u7535\u6e90", "forbidden": [],
        "causal_transitions": [_transition()],
        "chapter_contract_check": _all_contract_check_true(),
    }


def test_planner_v1_backward_compat():
    result = validate_planner_output(_planner_data_v1())
    assert result.planner_contract_version == 1


def test_planner_v2_accepts_complete_output():
    result = validate_planner_output(_planner_data_v2())
    assert result.planner_contract_version == 2
    assert result.scene_state.present_characters == ["\u6797\u9685"]
    assert result.concrete_problem == "\u6572\u51fb\u58f0\u6765\u6e90\u662f\u4ec0\u4e48"


def test_planner_v2_rejects_missing_scene_state():
    data = _planner_data_v2()
    del data["scene_state"]
    with pytest.raises(ValueError, match="scene_state is required"):
        validate_planner_output(data)


def test_planner_v2_rejects_missing_concrete_problem():
    data = _planner_data_v2()
    del data["concrete_problem"]
    with pytest.raises(ValueError, match="concrete_problem is required"):
        validate_planner_output(data)


def test_planner_v2_rejects_missing_character_interpretation():
    data = _planner_data_v2()
    data["causal_transitions"] = [{**_transition(), "character_interpretation": ""}]
    with pytest.raises(ValueError, match="character_interpretation is required"):
        validate_planner_output(data)


def test_planner_v2_rejects_same_state_delta():
    data = _planner_data_v2()
    data["causal_transitions"] = [{**_transition(), "state_delta": {"before": "\u76f8\u540c", "after": "\u76f8\u540c"}}]
    with pytest.raises(ValueError, match="state_delta.before and after must differ"):
        validate_planner_output(data)


def test_planner_v2_rejects_contract_check_false():
    data = _planner_data_v2()
    data["chapter_contract_check"] = {"function_aligned": False}
    with pytest.raises(ValueError, match="chapter_contract_check fields must all be true"):
        validate_planner_output(data)


def test_planner_v2_rejects_empty_contract_check():
    data = _planner_data_v2()
    data["chapter_contract_check"] = {}
    with pytest.raises(ValueError, match="chapter_contract_check fields must all be true"):
        validate_planner_output(data)


def test_planner_expected_version_rejects_wrong_version():
    data = _planner_data_v1()
    with pytest.raises(ValueError, match="expected planner_contract_version=2"):
        validate_planner_output(data, expected_version=2)


def test_planner_expected_version_accepts_correct_version():
    data = _planner_data_v2()
    result = validate_planner_output(data, expected_version=2)
    assert result.planner_contract_version == 2


def test_planner_v2_rejects_consequence_would_still_happen_true():
    data = _planner_data_v2()
    data["causal_transitions"] = [{**_transition(), "consequence_would_still_happen": True}]
    with pytest.raises(ValueError, match="consequence_would_still_happen must be false"):
        validate_planner_output(data)


def test_planner_v2_rejects_consequence_would_still_happen_none():
    data = _planner_data_v2()
    data["causal_transitions"] = [{**_transition(), "consequence_would_still_happen": None}]
    with pytest.raises(ValueError, match="consequence_would_still_happen must be false"):
        validate_planner_output(data)


def test_planner_v2_rejects_empty_state_delta_before():
    data = _planner_data_v2()
    data["causal_transitions"] = [{**_transition(), "state_delta": {"before": "", "after": "changed"}}]
    with pytest.raises(ValueError, match="state_delta.before must not be empty"):
        validate_planner_output(data)


def test_planner_v2_rejects_whitespace_only_state_delta():
    data = _planner_data_v2()
    data["causal_transitions"] = [{**_transition(), "state_delta": {"before": "  ", "after": "changed"}}]
    with pytest.raises(ValueError, match="state_delta.before must not be empty"):
        validate_planner_output(data)


def test_planner_v2_rejects_duplicate_next_constraint():
    data = _planner_data_v2()
    data["scene_state"]["already_existing_constraints"] = ["existing constraint"]
    data["causal_transitions"] = [{**_transition(), "next_constraint": "existing constraint"}]
    with pytest.raises(ValueError, match="next_constraint duplicates"):
        validate_planner_output(data)


def test_planner_v2_rejects_duplicate_next_constraint_with_punctuation():
    data = _planner_data_v2()
    data["scene_state"]["already_existing_constraints"] = ["existing constraint。"]
    data["causal_transitions"] = [{**_transition(), "next_constraint": "existing constraint"}]
    with pytest.raises(ValueError, match="next_constraint duplicates"):
        validate_planner_output(data)


def test_planner_v2_rejects_zero_causal_transitions():
    data = _planner_data_v2()
    data["causal_transitions"] = []
    with pytest.raises(ValueError, match="at least one causal_transition is required"):
        validate_planner_output(data)


# ── Planner v2 hardening: version gate, state_delta, constraints ──────


def test_planner_expected_version_rejects_missing_version_field():
    data = _planner_data_v2()
    del data["planner_contract_version"]
    with pytest.raises(ValueError, match="planner_contract_version is required"):
        validate_planner_output(data, expected_version=2)


def test_planner_expected_version_rejects_missing_version_field_on_v1_shape():
    # A v1-shaped payload (no version key at all) must fail loudly in the
    # current built-in workflow instead of silently defaulting to v1.
    data = _planner_data_v1()
    del data["planner_contract_version"]
    with pytest.raises(ValueError, match="planner_contract_version is required"):
        validate_planner_output(data, expected_version=2)


def test_planner_v1_passes_without_expected_version():
    # Legacy read path: historical v1 candidates stay readable when no
    # expected version is declared by the caller.
    result = validate_planner_output(_planner_data_v1())
    assert result.planner_contract_version == 1


def test_planner_v2_rejects_empty_state_delta_after():
    data = _planner_data_v2()
    data["causal_transitions"] = [{**_transition(), "state_delta": {"before": "局面改变", "after": ""}}]
    with pytest.raises(ValueError, match="state_delta.after must not be empty"):
        validate_planner_output(data)


def test_planner_v2_rejects_state_delta_trailing_whitespace_only_diff():
    data = _planner_data_v2()
    data["causal_transitions"] = [
        {**_transition(), "state_delta": {"before": "继续关门", "after": "继续关门 "}}
    ]
    with pytest.raises(ValueError, match="state_delta.before and after must differ"):
        validate_planner_output(data)


@pytest.mark.parametrize("before,after", [
    ("继续关门。", "继续关门"),
    ("继续关门", "继续关门。"),
    ("继续关门，", "继续关门"),
    ("door closed.", "door closed"),
    ("door closed;", "door closed"),
    ("Door Closed", "door closed"),
])
def test_planner_v2_rejects_state_delta_punctuation_or_case_only_diff(before, after):
    data = _planner_data_v2()
    data["causal_transitions"] = [
        {**_transition(), "state_delta": {"before": before, "after": after}}
    ]
    with pytest.raises(ValueError, match="state_delta.before and after must differ"):
        validate_planner_output(data)


def test_planner_v2_accepts_substantively_different_state_delta():
    data = _planner_data_v2()
    data["causal_transitions"] = [
        {**_transition(), "state_delta": {"before": "继续关门。", "after": "门被打开。"}}
    ]
    result = validate_planner_output(data)
    assert result.causal_transitions[0].state_delta.before == "继续关门。"


def test_planner_v2_rejects_duplicate_next_constraint_whitespace_collapsed():
    data = _planner_data_v2()
    data["scene_state"]["already_existing_constraints"] = ["existing constraint"]
    data["causal_transitions"] = [{**_transition(), "next_constraint": "existing   constraint"}]
    with pytest.raises(ValueError, match="next_constraint duplicates"):
        validate_planner_output(data)


def test_planner_v2_rejects_duplicate_next_constraint_case_insensitive():
    data = _planner_data_v2()
    data["scene_state"]["already_existing_constraints"] = ["Existing Constraint"]
    data["causal_transitions"] = [{**_transition(), "next_constraint": "existing constraint"}]
    with pytest.raises(ValueError, match="next_constraint duplicates"):
        validate_planner_output(data)


def test_planner_v2_rejects_duplicate_next_constraint_cjk_punctuation():
    data = _planner_data_v2()
    data["scene_state"]["already_existing_constraints"] = ["不能暴露身份。"]
    data["causal_transitions"] = [{**_transition(), "next_constraint": "不能暴露身份"}]
    with pytest.raises(ValueError, match="next_constraint duplicates"):
        validate_planner_output(data)


def test_planner_v2_accepts_genuinely_new_constraint():
    data = _planner_data_v2()
    data["scene_state"]["already_existing_constraints"] = ["不能暴露身份"]
    data["causal_transitions"] = [{**_transition(), "next_constraint": "必须在新守卫交班前离开"}]
    result = validate_planner_output(data)
    assert result.causal_transitions[0].next_constraint == "必须在新守卫交班前离开"


def test_planner_v2_full_valid_example_passes():
    data = _planner_data_v2()
    data["scene_state"]["already_existing_constraints"] = ["不能暴露身份"]
    result = validate_planner_output(data, expected_version=2)
    assert result.planner_contract_version == 2
    assert len(result.causal_transitions) == 1
    assert result.causal_transitions[0].consequence_would_still_happen is False


def test_planner_accepts_tempo_guardrails():
    result = validate_planner_output({**_planner_data_v1(), "tempo_guardrails": _tempo_guardrails()})
    assert result.tempo_guardrails.disclosure_cap == 1


def test_planner_normalizes_tempo_guardrail_machine_enums():
    guardrails = {
        **_tempo_guardrails(),
        "dominant_pressure": {
            **_tempo_guardrails()["dominant_pressure"],
            "kind": " Social_Friction ",
        },
        "stop_state": {
            **_tempo_guardrails()["stop_state"],
            "type": "RELATIONSHIP_SHIFT",
        },
    }

    result = validate_planner_output({**_planner_data_v1(), "tempo_guardrails": guardrails})

    assert result.tempo_guardrails.dominant_pressure.kind == "social_friction"
    assert result.tempo_guardrails.stop_state.type == "relationship_shift"


@pytest.mark.parametrize(
    "field,value",
    [
        ("dominant_pressure", "时间压力 + 沟通隔阂"),
        ("stop_state", "situational"),
        ("dominant_pressure", "social_friction + information_gap"),
    ],
)
def test_planner_rejects_non_enum_tempo_guardrail_machine_values(field, value):
    guardrails = _tempo_guardrails()
    guardrails[field] = {**guardrails[field], "kind" if field == "dominant_pressure" else "type": value}

    with pytest.raises(ValueError, match="PLANNER_OUTPUT_CONTRACT_INVALID"):
        validate_planner_output({**_planner_data_v1(), "tempo_guardrails": guardrails})


def test_planner_normalizes_single_unclassified_fact():
    guardrails = {**_tempo_guardrails(), "must_remain_unclassified": "\u6572\u51fb\u58f0\u6765\u6e90"}
    result = validate_planner_output({**_planner_data_v1(), "tempo_guardrails": guardrails})
    assert result.tempo_guardrails.must_remain_unclassified == ["\u6572\u51fb\u58f0\u6765\u6e90"]


def test_tempo_final_line_requires_explicit_visible_marker():
    guardrails = {**_tempo_guardrails(), "final_line_must_include": "\u8eab\u4efd\u9a8c\u8bc1\u901a\u8fc7"}
    validate_tempo_final_line("\u9762\u677f\u4eae\u4e86\u3002\n\n\u8eab\u4efd\u9a8c\u8bc1\u901a\u8fc7\u3002", guardrails)
    with pytest.raises(ValueError, match="TEMPO_FINAL_LINE_MISMATCH"):
        validate_tempo_final_line("\u8eab\u4efd\u9a8c\u8bc1\u901a\u8fc7\u3002\n\n\u4ed6\u53ea\u80fd\u7ee7\u7eed\u770b\u7740\u3002", guardrails)


@pytest.mark.parametrize("guardrails", [
    {**_tempo_guardrails(), "disclosure_cap": 2},
    {key: value for key, value in _tempo_guardrails().items() if key != "stop_state"},
])
def test_planner_rejects_invalid_tempo_guardrails(guardrails):
    with pytest.raises(ValueError, match="PLANNER_OUTPUT_CONTRACT_INVALID"):
        validate_planner_output({**_planner_data_v1(), "tempo_guardrails": guardrails})


def test_planner_normalizes_common_real_llm_shape_variants():
    data = {
        **_planner_data_v1(),
        "characters": ["\u9996\u5e2d\u7ef4\u4fee\u5458\u6797\u9685", {"name": "\u95e8\u63a7\u7cfb\u7edf", "goal": "\u7ef4\u6301\u95e8\u7981"}],
        "causal_transitions": [{
            **_transition(),
            "id": "ct_01",
            "reader_must_infer": ["\u6572\u51fb\u58f0\u4e0d\u662f\u666e\u901a\u6545\u969c", "\u6797\u9685\u4e0d\u613f\u6df1\u7a76"],
            "narrator_must_not_state": "\u6572\u51fb\u58f0\u7684\u771f\u5b9e\u6765\u6e90\u3002",
        }],
        "chapter_contract_check": "xxx",
    }

    result = validate_planner_output(data)

    assert result.characters[0] == {"name": "\u9996\u5e2d\u7ef4\u4fee\u5458\u6797\u9685"}
    assert result.causal_transitions[0].id == "CT01"
    assert result.causal_transitions[0].reader_must_infer == "\u6572\u51fb\u58f0\u4e0d\u662f\u666e\u901a\u6545\u969c\uff1b\u6797\u9685\u4e0d\u613f\u6df1\u7a76"
    assert result.causal_transitions[0].narrator_must_not_state == ["\u6572\u51fb\u58f0\u7684\u771f\u5b9e\u6765\u6e90\u3002"]


def test_planner_normalizes_character_name_map_without_losing_fields():
    data = _planner_data_v2()
    data["characters"] = {
        "老陈": {"goal": "帮助女孩", "known": ["她站在门外"]},
        "女孩": {"name": "小满", "goal": "找地方暂时停留"},
    }

    result = validate_planner_output(data, expected_version=2)

    assert result.characters == [
        {"name": "老陈", "goal": "帮助女孩", "known": ["她站在门外"]},
        {"name": "小满", "goal": "找地方暂时停留"},
    ]


def test_planner_rejects_character_name_map_with_non_object_value():
    data = _planner_data_v2()
    data["characters"] = {"老陈": "帮助女孩"}

    with pytest.raises(ValueError, match="PLANNER_OUTPUT_CONTRACT_INVALID"):
        validate_planner_output(data, expected_version=2)


@pytest.mark.parametrize("field", ["pressure", "end_condition"])
def test_planner_rejects_top_level_object_fields_that_must_remain_strings(field):
    data = _planner_data_v2()
    data[field] = {"description": "关店时间逼近"}

    with pytest.raises(ValueError, match="PLANNER_OUTPUT_CONTRACT_INVALID"):
        validate_planner_output(data, expected_version=2)


def test_planner_normalizes_grouped_forbidden_values():
    data = {
        "planner_contract_version": 1,
        "scene_goal": "\u63a8\u8fdb\u7ebf\u7d22",
        "location": "\u60ac\u7a7a\u6b65\u9053",
        "time": "\u6df1\u591c",
        "characters": [],
        "pressure": ["\u91cd\u529b\u5373\u5c06\u5931\u6548", "\u8bb8\u6800\u60ac\u5728\u6b65\u9053\u5916\u4fa7"],
        "turning_point": "\u9646\u8861\u5f00\u59cb\u8ffd\u67e5",
        "end_condition": "\u672a\u6765\u65f6\u95f4\u6233\u51fa\u73b0",
        "forbidden": {
            "must_not_deliver": ["\u4e0d\u89e3\u91ca\u7f16\u53f7\u5173\u7cfb"],
            "fuel_reserved": ["\u4e0d\u63ed\u6653\u53d1\u9001\u8005"],
        },
        "causal_transitions": [_transition()],
        "chapter_contract_check": {},
    }

    result = validate_planner_output(data)

    assert result.forbidden == ["\u4e0d\u89e3\u91ca\u7f16\u53f7\u5173\u7cfb", "\u4e0d\u63ed\u6653\u53d1\u9001\u8005"]
    assert result.pressure == "\u91cd\u529b\u5373\u5c06\u5931\u6548\uff1b\u8bb8\u6800\u60ac\u5728\u6b65\u9053\u5916\u4fa7"


def test_critic_causal_check_accepts_numbered_paragraph_labels():
    data = {
        "overall_assessment": "\u56e0\u679c\u8f6c\u6298\u6210\u7acb",
        "decision": "pass",
        "strengths": ["\u5931\u91cd\u5371\u673a\u573a\u666f\u7684\u7269\u7406\u63cf\u5199\u51c6\u786e\u3002"],
        "issues": [
            {
                "issue_id": "I01",
                "severity": "high",
                "issue_type": "inference_overexplained",
                "paragraph_ids": [71],
                "problem": "\u65c1\u767d\u63d0\u524d\u89e3\u91ca\u65b9\u6848\u3002",
                "revision_goal": "\u5220\u9664\u89e3\u91ca\uff0c\u4fdd\u7559\u9009\u62e9\u3002",
                "recommended_operation": "withhold_inference",
            }
        ],
        "protected_strengths": [
            {
                "paragraph_id": "P001-P002",
                "reason": "\u8bc1\u636e\u540e\u76f4\u63a5\u6539\u53d8\u884c\u52a8",
                "strength_type": "reader_inference_gap",
            }
        ],
        "chapter_contract_check": {},
        "causal_transition_check": [
            {
                "transition_id": "CT01",
                "trigger_visible": True,
                "next_action_changed": True,
                "reader_inference_withheld": True,
                "forbidden_explanation_found": True,
                "consequence_visible": True,
                "next_constraint_preserved": True,
                "paragraph_ids": ["P001", "P002"],
                "result": "fail",
                "comment": "\u53d1\u73b0\u89e3\u91ca",
            }
        ],
    }

    result = validate_critic_output(data)

    assert result.strengths == ["\u5931\u91cd\u5371\u673a\u573a\u666f\u7684\u7269\u7406\u63cf\u5199\u51c6\u786e\u3002"]
    assert result.issues[0].paragraph_ids == ["P071"]
    assert result.protected_strengths[0].paragraph_ids == ["P001", "P002"]
    assert result.causal_transition_check[0].paragraph_ids == ["P001", "P002"]
    assert result.causal_transition_check[0].forbidden_explanation_found


def test_reviser_patch_accepts_integer_paragraph_ids():
    data = {
        "patches": [
            {
                "issue_id": "I01",
                "operation": "replace",
                "target_paragraph_ids": [71, 72],
                "replacement": "\u4fee\u6539\u540e\u7684\u6bb5\u843d\u3002",
            }
        ],
        "revised_text": "\u4fee\u6539\u540e\u7684\u5b8c\u6574\u6b63\u6587\u3002",
        "unchanged_ratio": 0.9,
        "introduced_facts": [],
        "contract_verification": {},
    }

    result = validate_reviser_output(data)

    assert result.patches[0].target_paragraph_ids == ["P071", "P072"]


@pytest.mark.parametrize("issue_type, operation", [
    ("narrator_character_label", "de_label"),
    ("clue_conveyor_belt", "de_chain"),
    ("formulaic_escalation", "de_chain"),
    ("premature_classification", "de_chain"),
    ("closing_summary_hook", "tighten"),
])
def test_critic_accepts_tempo_issue_types(issue_type, operation):
    result = validate_critic_output({
        "overall_assessment": "x", "decision": "local_revision", "strengths": [],
        "protected_strengths": [], "chapter_contract_check": {}, "causal_transition_check": [],
        "issues": [{
            "issue_id": "I01", "severity": "medium", "issue_type": issue_type,
            "paragraph_ids": [1], "problem": "x", "revision_goal": "x",
            "recommended_operation": operation,
        }],
    })
    assert result.issues[0].issue_type.value == issue_type


def test_judge_rejects_unselected_issue_results_and_numbered_merged_text():
    data = {
        "decision": "accept_merged",
        "issue_results": [
            {"issue_id": "I01", "status": "resolved", "action": "keep_revision"},
            {"issue_id": "I02", "status": "resolved", "action": "keep_revision"},
        ],
        "new_problems": [],
        "revision_became_cleaner_but_flatter": False,
        "author_intent_preserved": True,
        "chapter_contract_completed": True,
        "main_payoff_preserved": True,
        "final_text": "[P001] \u9762\u677f\u4eae\u4e86\u3002",
        "quality_score": 80,
        "state_patch": {},
    }

    with pytest.raises(ValueError, match="JUDGE_OUTPUT_CONTRACT_INVALID"):
        validate_judge_output_for_selected_issues(data, ["I01"])


def test_judge_accepts_exact_selected_issue_results_and_clean_merged_text():
    data = {
        "decision": "accept_merged",
        "issue_results": [
            {"issue_id": "I01", "status": "resolved", "action": "keep_revision"},
        ],
        "new_problems": [],
        "revision_became_cleaner_but_flatter": False,
        "author_intent_preserved": True,
        "chapter_contract_completed": True,
        "main_payoff_preserved": True,
        "final_text": "\u9762\u677f\u4eae\u4e86\u3002",
        "quality_score": 80,
        "state_patch": {},
    }

    result = validate_judge_output_for_selected_issues(data, ["I01"])

    assert result.decision.value == "accept_merged"
