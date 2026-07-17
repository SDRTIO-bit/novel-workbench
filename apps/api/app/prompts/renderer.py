import re

ALLOWED_VARIABLES = {
    "project",
    "project_documents",
    "chapter",
    "recent_chapters",
    "selected_chapters",
    "scene_instruction",
    "run_override",
    "scene_plan",
    "draft_text",
    "numbered_draft",
    "critic_report",
    "selected_issues",
    "revised_text",
    "project_name",
    "project_genre",
    "author_note",
    "default_pov",
    "chapter_title",
    "chapter_text",
    "chapter_function",
    "arc_phase",
    "reader_comes_for",
    "must_deliver",
    "must_not_deliver",
    "main_change",
    "main_payoff",
    "ending_hook",
    "hook_type",
    "fuel_reserved_for_later",
    "target_length",
    "write_mode",
    "continuation_anchor",
    "current_chapter_text",
    "tempo_guardrails",
}


def _find_variables(template: str) -> set[str]:
    return set(re.findall(r"\{\{(\w+)\}\}", template))


def validate_variables(template: str) -> list[str]:
    used = _find_variables(template)
    invalid = used - ALLOWED_VARIABLES
    if invalid:
        return [f"未定义的模板变量: {v}" for v in sorted(invalid)]
    return []


def render(template: str, variables: dict[str, str], *, strict: bool = True) -> str:
    if strict:
        errors = validate_variables(template)
        if errors:
            raise RenderError(errors)

    result = template
    for name, value in variables.items():
        result = result.replace("{{" + name + "}}", value)
    return result


class RenderError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))
