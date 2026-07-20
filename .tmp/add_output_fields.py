with open('app/prompts/defaults.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the planner system_template end (line with ")," after system_template)
planner_start = None
planner_end = None
for i, line in enumerate(lines):
    if '"planner"' in line:
        for j in range(i, min(i+200, len(lines))):
            if 'system_template' in lines[j]:
                planner_start = j
            if planner_start and lines[j].strip() == '),' and j > planner_start:
                planner_end = j
                break
        break

print(f"Planner system_template: lines {planner_start+1} to {planner_end+1}")

# Insert the output fields section before "## 项目设定"
# Find the line with "## 项目设定"
project_section_line = None
for i in range(planner_start, planner_end):
    if '## \u9879\u76ee\u8bbe\u5b9a' in lines[i]:
        project_section_line = i
        break

print(f"Found '## \u9879\u76ee\u8bbe\u5b9a' at line {project_section_line+1}")

# Insert the output fields section
output_fields_section = [
    '            "\u8f93\u51fa JSON \u5b57\u6bb5\uff1a\\n"\n',
    '            "- scene_goal\u3001location\u3001time\u3001characters\u3001pressure\u3001turning_point\u3001end_condition\u3001forbidden\uff1a\u57fa\u672c\u573a\u666f\u89c4\u5212\u5b57\u6bb5\\n"\n',
    '            "- scene_state\uff08\u53ef\u9009\uff09\uff1a\u573a\u666f\u5165\u53e3\u72b6\u6001\uff0c\u5305\u542b last_completed_action\u3001present_characters\u3001visible_facts\u3001available_objects\u3001unresolved_problem\u3001already_existing_constraints\\n"\n',
    '            "- concrete_problem\uff1a\u89d2\u8272\u5728\u672c\u573a\u666f\u4e2d\u9762\u5bf9\u7684\u5177\u4f53\u3001\u53ef\u64cd\u4f5c\u7684\u95ee\u9898\\n"\n',
    '            "- causal_transitions\uff1a\u56e0\u679c\u8f6c\u6298\u6570\u7ec4\uff080\u20143 \u9879\uff09\uff0c\u6bcf\u9879\u5fc5\u987b\u5305\u542b id\u3001kind\u3001visible_trigger\u3001character_interpretation\u3001character_next_action\u3001rejected_alternative\u3001immediate_consequence\u3001counterfactual_without_action\u3001state_delta\uff08{before, after}\uff09\u3001cost_or_commitment\u3001next_constraint\u3001reader_must_infer\u3001narrator_must_not_state\\n"\n',
    '            "- tempo_guardrails\uff08\u53ef\u9009\uff09\uff1a\u5305\u542b entry_pressure\u3001dominant_pressure\uff08{kind, description}\uff09\u3001allowed_viewpoint_misread\u3001disclosure_cap\u3001must_remain_unclassified\u3001stop_state\uff08{type, visible_fact, what_is_now_different, must_not_append}\uff09\u3001final_line_must_include\\n"\n',
    '            "- chapter_contract_check\uff1a\u5951\u7ea6\u68c0\u67e5\uff0c\u6240\u6709\u5b57\u6bb5\u4e3a bool\\n\\n"\n',
]

# Insert before the project section
new_lines = lines[:project_section_line] + output_fields_section + lines[project_section_line:]

with open('app/prompts/defaults.py', 'w', encoding='utf-8', newline='\r\n') as f:
    f.writelines(new_lines)

print("Added output fields section")

# Verify
import importlib.util
spec = importlib.util.spec_from_file_location("defaults", "app/prompts/defaults.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print(f"Planner system_template: {len(mod.BUILTIN_PROMPTS[0]['system_template'])} chars")
