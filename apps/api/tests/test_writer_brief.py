from app.services.writer_brief import compile_writer_brief


def test_writer_brief_excludes_planner_hidden_answers():
    brief = compile_writer_brief({
        "scene_goal": "处理扣错的校服",
        "reader_must_infer": "后台答案",
        "causal_transitions": [{
            "id": "CT01",
            "visible_trigger": "班长点名时看见扣子",
            "character_next_action": "把书递过去遮住胸前",
            "reader_must_infer": "他怕公开出丑",
            "narrator_must_not_state": ["他很羞愧"],
        }],
        "tempo_guardrails": {
            "entry_pressure": "点名开始",
            "allowed_viewpoint_misread": "后台判断",
            "must_remain_unclassified": ["后台秘密"],
            "stop_state": {"visible_fact": "扣子被遮住", "what_is_now_different": "无法解释"},
        },
    })

    serialized = str(brief)
    assert "班长点名时看见扣子" in serialized
    assert "reader_must_infer" not in serialized
    assert "narrator_must_not_state" not in serialized
    assert "后台答案" not in serialized
    assert "后台判断" not in serialized
    assert "后台秘密" not in serialized
