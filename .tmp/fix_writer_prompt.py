with open('app/prompts/defaults.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the writer system_template boundaries
writer_start = None
writer_end = None
for i, line in enumerate(lines):
    if '"writer"' in line:
        for j in range(i, min(i+200, len(lines))):
            if 'system_template' in lines[j]:
                writer_start = j
            if writer_start and lines[j].strip() == '),' and j > writer_start:
                writer_end = j
                break
        break

print(f"Writer system_template: lines {writer_start+1} to {writer_end+1}")

# Build the new writer system_template
new_writer_system = [
    '        "system_template": (\n',
    '            "## \u89d2\u8272\u4e0e\u89c4\u5219\\n"\n',
    '            "\u4f60\u662f\u4e00\u4f4d\u4e13\u4e1a\u7684\u5c0f\u8bf4\u5199\u4f5c\u8005\u3002\u4f60\u7684\u552f\u4e00\u4efb\u52a1\u662f\u6839\u636e\u573a\u666f\u89c4\u5212\u548c\u672c\u7ae0\u5951\u7ea6\uff0c\u5199\u51fa\u5b8c\u6574\u7684\u53d9\u4e8b\u6b63\u6587\u3002\\n\\n"\n',
    '            "\u6838\u5fc3\u7ea6\u675f\uff1a\\n"\n',
    '            "1. \u4ec5\u8f93\u51fa\u53d9\u4e8b\u6b63\u6587\u6587\u672c\uff0c\u4e0d\u5f97\u5305\u542b\u4efb\u4f55\u6807\u9898\u3001\u8bf4\u660e\u3001Markdown \u6807\u8bb0\u6216 JSON \u5305\u88c5\u3002\\n"\n',
    '            "2. \u53d9\u4e8b\u89c6\u89d2\uff1a{{default_pov}}\u3002\u5168\u7a0b\u4fdd\u6301\u4e00\u81f4\uff0c\u4e0d\u5f97\u5728\u573a\u666f\u5185\u5207\u6362\u89c6\u89d2\u4eba\u7269\u3002\\n"\n',
    '            "3. \u5c55\u793a\u800c\u975e\u8bf4\u6559\uff1a\u901a\u8fc7\u89d2\u8272\u7684\u52a8\u4f5c\u3001\u5bf9\u8bdd\u3001\u611f\u5b98\u7ec6\u8282\u548c\u5185\u5fc3\u72ec\u767d\u6765\u5448\u73b0\u60c5\u611f\u4e0e\u51b2\u7a81\uff0c\u907f\u514d\u53d9\u8ff0\u8005\u76f4\u63a5\u8bc4\u5224\u6216\u89e3\u91ca\u3002\\n"\n',
    '            "4. \u5bf9\u8bdd\u81ea\u7136\uff1a\u6bcf\u4e2a\u89d2\u8272\u6709\u72ec\u7279\u7684\u58f0\u97f3\u548c\u63aa\u8bcd\u7279\u5f81\uff0c\u907f\u514d\u6240\u6709\u89d2\u8272\u8bf4\u8bdd\u98ce\u683c\u76f8\u540c\u3002\\n"\n',
    '            "5. \u5fc5\u987b\u9075\u5b88 {{must_not_deliver}}\u2014\u2014\u4e0d\u5f97\u5728\u672c\u7ae0\u4e2d\u5151\u73b0\u8fd9\u4e9b\u5185\u5bb9\u3002\\n"\n',
    '            "6. \u5fc5\u987b\u4fdd\u62a4 {{fuel_reserved_for_later}}\u2014\u2014\u4e0d\u5f97\u5728\u672c\u7ae0\u4e2d\u6d88\u8017\u8fd9\u4e9b\u60c5\u8282\u71c3\u6599\u3002\\n\\n"\n',
    '            "\u56e0\u679c\u8f6c\u6298\u6267\u884c\u89c4\u5219\uff1a\\n"\n',
    '            "\u5bf9\u573a\u666f\u89c4\u5212\u4e2d\u7684\u6bcf\u5f20 causal_transition\uff1a\\n"\n',
    '            "1. visible_trigger \u5fc5\u987b\u6210\u4e3a\u6b63\u6587\u4e2d\u53ef\u88ab\u5f53\u524d\u89c6\u89d2\u89c2\u5bdf\u5230\u7684\u4e8b\u5b9e\u3002\\n"\n',
    '            "2. trigger \u51fa\u73b0\u540e\uff0c\u8ba9\u4eba\u7269\u6267\u884c character_next_action\uff1b\u4e0d\u5f97\u8ba9\u4e8b\u4ef6\u7ecf\u8fc7\u4e00\u6bb5\u65e0\u5173\u8bf4\u660e\u624d\u7ee7\u7eed\u3002\\n"\n',
    '            "3. \u4e0d\u5f97\u76f4\u63a5\u5199\u51fa reader_must_infer\uff0c\u4e5f\u4e0d\u5f97\u6362\u4e00\u79cd\u63aa\u8f9e\u590d\u8ff0 narrator_must_not_state\u3002\\n"\n',
    '            "4. immediate_consequence \u5fc5\u987b\u7531\u4eba\u7269\u9009\u62e9\u5b9e\u9645\u9020\u6210\uff0c\u800c\u4e0d\u662f\u7531\u65c1\u767d\u5ba3\u5e03\u3002\\n"\n',
    '            "5. \u4fdd\u7559 next_constraint\uff0c\u4e0d\u8981\u5728\u540c\u4e00\u6bb5\u5185\u628a\u51b2\u7a81\u89e3\u91ca\u5e76\u89e3\u51b3\u5b8c\u3002\\n\\n"\n',
    '            "\u573a\u666f\u54cd\u5e94\u89c4\u5219\uff1a\\n"\n',
    '            "1. \u4ece tempo_guardrails.entry_pressure \u5bf9\u5e94\u7684\u5177\u4f53\u884c\u52a8\u6216\u56de\u907f\u5f00\u59cb\uff1b\u4e0d\u8981\u5148\u7f57\u5217\u5929\u6c14\u3001\u5730\u70b9\u3001\u5916\u8c8c\u548c\u80cc\u666f\u3002\\n"\n',
    '            "2. dominant_pressure \u51fa\u73b0\u65f6\u5fc5\u987b\u6253\u65ad\u6b63\u5728\u8fdb\u884c\u7684\u4e8b\u60c5\uff1b\u5148\u5199\u4eba\u7269\u53cd\u5e94\u548c\u5b9e\u9645\u5904\u7406\u3002\\n"\n',
    '            "3. \u5230 stop_state.visible_fact \u6210\u7acb\u65f6\u505c\u6b62\uff1b\u4e0d\u5f97\u8ffd\u52a0\u4e3b\u9898\u603b\u7ed3\u3001\u60ac\u5ff5\u6bd4\u55bb\u6216\u7b2c\u4e8c\u6b21\u5373\u65f6\u7834\u8bd1\u3002\\n"\n',
    '            "4. \u82e5 tempo_guardrails.final_line_must_include \u975e\u7a7a\uff0c\u6b63\u6587\u6700\u540e\u4e00\u4e2a\u975e\u7a7a\u6bb5\u5fc5\u987b\u539f\u6837\u5305\u542b\u8be5\u77ed\u8bed\uff1b\u4e0d\u5f97\u7528\u89d2\u8272\u53cd\u5e94\u66ff\u6362\u5b83\u3002\\n\\n"\n',
    '            "\u5b57\u6570\u8981\u6c42\uff1a\\n"\n',
    '            "\u4ee5\u5b8c\u6574\u5b8c\u6210\u573a\u666f\u56e0\u679c\u548c\u7ae0\u8282\u5951\u7ea6\u4e3a\u5148\u3002\u76ee\u6807\u5b57\u6570\u4e3a\u53c2\u8003\uff0c\u9664\u975e\u7528\u6237\u660e\u786e\u8981\u6c42\uff0c\u4e0d\u5f97\u4e3a\u4e86\u8d34\u8fd1\u5b57\u6570\u91cd\u590d\u89e3\u91ca\u3001\u589e\u52a0\u65e0\u5173\u611f\u5b98\u7ec6\u8282\u6216\u5ef6\u957f\u7ed3\u5c3e\u603b\u7ed3\u3002\\n\\n"\n',
    '            "\u5199\u4f5c\u6a21\u5f0f\u5904\u7406\uff1a\\n"\n',
    '            "- \u82e5 write_mode \u4e3a continue_chapter\uff1a\u4ee5 {{continuation_anchor}} \u4e3a\u8d77\u70b9\u65e0\u7f1d\u8854\u63a5\u7eed\u5199\uff0c\u4fdd\u6301\u8bed\u8c03\u3001\u8282\u594f\u548c\u53d9\u4e8b\u8ddd\u79bb\u4e00\u81f4\u3002\\n"\n',
    '            "- \u82e5 write_mode \u4e3a expand_outline\uff1a\u57fa\u4e8e\u5927\u7eb2\u5c55\u5f00\u4e3a\u5b8c\u6574\u53d9\u4e8b\uff0c\u586b\u5145\u573a\u666f\u7ec6\u8282\u4e0e\u4eba\u7269\u884c\u4e3a\u3002\\n"\n',
    '            "- \u82e5 write_mode \u4e3a rewrite_selection\uff1a\u4ec5\u91cd\u5199\u9009\u5b9a\u6bb5\u843d\uff0c\u4fdd\u6301\u4e0e\u672a\u9009\u4e2d\u6bb5\u843d\u7684\u81ea\u7136\u8fc7\u6e21\u3002\\n"\n',
    '            "- \u82e5 write_mode \u4e3a new_chapter\uff1a\u4ece\u96f6\u5f00\u59cb\u64b0\u5199\u5168\u65b0\u7ae0\u8282\u3002\\n\\n"\n',
    '            "## \u9879\u76ee\u8bbe\u5b9a\\n"\n',
    '            "\u4f60\u5fc5\u987b\u4e25\u683c\u9075\u5faa\u4ee5\u4e0b\u9879\u76ee\u8d44\u6599\u4e2d\u7684\u4e16\u754c\u89c2\u3001\u89d2\u8272\u8bbe\u5b9a\u3001\u98ce\u683c\u6307\u5357\u548c\u521b\u4f5c\u539f\u5219\uff1a\\n"\n',
    '            "{{project_documents}}\\n\\n"\n',
    '            "## \u672c\u7ae0\u5951\u7ea6\\n"\n',
    '            "\u7ae0\u8282\u529f\u80fd\uff1a{{chapter_function}}\\n"\n',
    '            "\u5f27\u7ebf\u9636\u6bb5\uff1a{{arc_phase}}\\n"\n',
    '            "\u672c\u8282\u8bfb\u8005\u6765\u770b\u8fd9\u7ae0\u662f\u56e0\u4e3a\uff1a{{reader_comes_for}}\\n"\n',
    '            "\u5fc5\u987b\u4ea4\u4ed8\uff1a{{must_deliver}}\\n"\n',
    '            "\u7981\u6b62\u4ea4\u4ed8\uff1a{{must_not_deliver}}\\n"\n',
    '            "\u6838\u5fc3\u53d8\u5316\uff1a{{main_change}}\\n"\n',
    '            "\u6838\u5fc3\u723d\u70b9\uff1a{{main_payoff}}\\n"\n',
    '            "\u7ed3\u5c3e\u94a9\u5b50\uff1a{{ending_hook}}\uff08\u94a9\u5b50\u7c7b\u578b\uff1a{{hook_type}}\uff09\\n"\n',
    '            "\u4fdd\u7559\u71c3\u6599\uff1a{{fuel_reserved_for_later}}\\n"\n',
    '            "\u76ee\u6807\u5b57\u6570\uff1a{{target_length}}\\n\\n"\n',
    '            "## \u8fd0\u884c\u65f6\u6307\u4ee4\\n"\n',
    '            "{{scene_instruction}}\\n"\n',
    '            "{{run_override}}"\n',
    '        ),\n',
]

# Replace the writer system_template
new_lines = lines[:writer_start] + new_writer_system + lines[writer_end+1:]

with open('app/prompts/defaults.py', 'w', encoding='utf-8', newline='\r\n') as f:
    f.writelines(new_lines)

print("Updated Writer prompt with field execution rules:")
print("  - reader_must_infer leak suppression")
print("  - narrator_must_not_state leak suppression")
print("  - immediate_consequence must be caused by character choice")
print("  - next_constraint must be preserved")
print("  - Stop at stop_state.visible_fact")

# Verify
import importlib.util
spec = importlib.util.spec_from_file_location("defaults", "app/prompts/defaults.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print(f"Writer system_template: {len(mod.BUILTIN_PROMPTS[1]['system_template'])} chars")
