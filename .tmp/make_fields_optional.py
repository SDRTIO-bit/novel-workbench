with open('app/llm/output_contracts.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Make StateDelta fields optional
old_state_delta = '''class StateDelta(BaseModel):
    before: str = Field(min_length=1)
    after: str = Field(min_length=1)'''

new_state_delta = '''class StateDelta(BaseModel):
    before: str = ""
    after: str = ""'''

content = content.replace(old_state_delta, new_state_delta)

# Make CausalTransition new fields optional
old_causal = '''class CausalTransition(BaseModel):
    id: str
    kind: CausalTransitionKind
    visible_trigger: str = Field(min_length=1)
    character_interpretation: str = Field(min_length=1)
    character_next_action: str = Field(min_length=1)
    rejected_alternative: str = Field(min_length=1)
    immediate_consequence: str = Field(min_length=1)
    counterfactual_without_action: str = Field(min_length=1)
    state_delta: StateDelta
    cost_or_commitment: str = Field(min_length=1)
    next_constraint: str = Field(min_length=1)
    reader_must_infer: str = Field(min_length=1)
    narrator_must_not_state: list[str] = Field(min_length=1)'''

new_causal = '''class CausalTransition(BaseModel):
    id: str
    kind: CausalTransitionKind
    visible_trigger: str = Field(min_length=1)
    character_interpretation: str = ""
    character_next_action: str = Field(min_length=1)
    rejected_alternative: str = ""
    immediate_consequence: str = Field(min_length=1)
    counterfactual_without_action: str = ""
    state_delta: StateDelta | None = None
    cost_or_commitment: str = ""
    next_constraint: str = Field(min_length=1)
    reader_must_infer: str = Field(min_length=1)
    narrator_must_not_state: list[str] = Field(min_length=1)'''

content = content.replace(old_causal, new_causal)

with open('app/llm/output_contracts.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated output_contracts.py - made new fields optional")

# Verify
from app.llm.output_contracts import CausalTransition, StateDelta
print(f"StateDelta fields: {list(StateDelta.model_fields.keys())}")
print(f"CausalTransition fields: {list(CausalTransition.model_fields.keys())}")
