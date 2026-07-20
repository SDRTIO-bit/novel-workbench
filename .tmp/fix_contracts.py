with open('app/llm/output_contracts.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Change chapter_contract_check defaults from True to False
old_contract_check = '''class PlannerChapterContractCheck(BaseModel):
    function_aligned: bool = True
    must_deliver_covered: bool = True
    must_not_deliver_respected: bool = True
    main_change_enabled: bool = True
    main_payoff_prepared: bool = True
    ending_hook_established: bool = True
    causal_transitions_grounded: bool = True
    reader_inference_not_pre_resolved: bool = True
    scene_state_reconstructed: bool = True
    information_sources_legal: bool = True
    character_choice_is_real: bool = True
    consequence_is_counterfactual: bool = True
    state_delta_is_nonempty: bool = True
    next_constraint_is_new: bool = True
    stop_state_is_visible: bool = True
    stop_state_changes_future_actions: bool = True'''

new_contract_check = '''class PlannerChapterContractCheck(BaseModel):
    function_aligned: bool = False
    must_deliver_covered: bool = False
    must_not_deliver_respected: bool = False
    main_change_enabled: bool = False
    main_payoff_prepared: bool = False
    ending_hook_established: bool = False
    causal_transitions_grounded: bool = False
    reader_inference_not_pre_resolved: bool = False
    scene_state_reconstructed: bool = False
    information_sources_legal: bool = False
    character_choice_is_real: bool = False
    consequence_is_counterfactual: bool = False
    state_delta_is_nonempty: bool = False
    next_constraint_is_new: bool = False
    stop_state_is_visible: bool = False
    stop_state_changes_future_actions: bool = False'''

content = content.replace(old_contract_check, new_contract_check)

# 2. Add planner_contract_version field to PlannerOutput
old_planner_output_start = '''class PlannerOutput(BaseModel):
    scene_goal: str = ""
    location: str = ""
    time: str = ""
    scene_state: SceneState | None = None'''

new_planner_output_start = '''class PlannerOutput(BaseModel):
    planner_contract_version: int = 1
    scene_goal: str = ""
    location: str = ""
    time: str = ""
    scene_state: SceneState | None = None'''

content = content.replace(old_planner_output_start, new_planner_output_start)

# 3. Update validate_planner_output to enforce v2 contract
old_validate = '''def validate_planner_output(data: dict) -> PlannerOutput:
    try:
        return PlannerOutput(**data)
    except Exception as e:
        raise ValueError(f"PLANNER_OUTPUT_CONTRACT_INVALID: {e}") from e'''

new_validate = '''def validate_planner_output(data: dict) -> PlannerOutput:
    try:
        output = PlannerOutput(**data)
    except Exception as e:
        raise ValueError(f"PLANNER_OUTPUT_CONTRACT_INVALID: {e}") from e
    
    version = output.planner_contract_version
    if version >= 2:
        errors = []
        
        if not output.scene_state:
            errors.append("scene_state is required in v2")
        elif not output.scene_state.present_characters:
            errors.append("scene_state.present_characters must not be empty")
        elif not output.scene_state.visible_facts:
            errors.append("scene_state.visible_facts must not be empty")
        
        if not output.concrete_problem:
            errors.append("concrete_problem is required in v2")
        
        for i, ct in enumerate(output.causal_transitions):
            if not ct.character_interpretation:
                errors.append(f"causal_transitions[{i}].character_interpretation is required in v2")
            if not ct.rejected_alternative:
                errors.append(f"causal_transitions[{i}].rejected_alternative is required in v2")
            if not ct.counterfactual_without_action:
                errors.append(f"causal_transitions[{i}].counterfactual_without_action is required in v2")
            if not ct.state_delta:
                errors.append(f"causal_transitions[{i}].state_delta is required in v2")
            elif ct.state_delta.before == ct.state_delta.after:
                errors.append(f"causal_transitions[{i}].state_delta.before/after must differ")
            if not ct.cost_or_commitment:
                errors.append(f"causal_transitions[{i}].cost_or_commitment is required in v2")
        
        if output.tempo_guardrails:
            if not output.tempo_guardrails.stop_state:
                errors.append("tempo_guardrails.stop_state is required when tempo_guardrails present")
        
        contract_check = output.chapter_contract_check
        failing_fields = []
        for field_name in contract_check.model_fields:
            if not getattr(contract_check, field_name):
                failing_fields.append(field_name)
        if failing_fields:
            errors.append(f"chapter_contract_check fields must all be true, but these are false: {failing_fields}")
        
        if errors:
            raise ValueError(f"PLANNER_OUTPUT_CONTRACT_INVALID (v2): {'; '.join(errors)}")
    
    return output'''

content = content.replace(old_validate, new_validate)

with open('app/llm/output_contracts.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated output_contracts.py:")
print("  - chapter_contract_check defaults changed to False")
print("  - Added planner_contract_version field (default=1)")
print("  - Added v2 validation logic")
