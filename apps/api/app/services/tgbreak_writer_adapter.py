from dataclasses import dataclass
from typing import Mapping

from app.tgbreak.renderer import adapt_project_variables


NOVEL_MODE_CONTEXT = (
    "当前为作者级小说创作，不是单角色 RP。\n\n"
    "作者要求可以规定任意虚构角色和场景事件；\n"
    "但每个角色在正文中仍只能依据自己已经知道、看到或听到的信息行动。"
)


@dataclass(frozen=True)
class TGBreakProjectData:
    variables: dict[str, str]
    selected_planner_candidate_id: str | None


def _section(title: str, value: object) -> str:
    text = "" if value is None else str(value).strip()
    return f"## {title}\n{text}" if text else ""


def build_tgbreak_project_data_from_writer_context(
    writer_context: Mapping[str, object],
    *,
    selected_planner_candidate_id: str | None,
) -> TGBreakProjectData:
    """Map the already-resolved Writer context into TGbreak variables.

    This adapter performs deterministic formatting only. It deliberately reads
    no database rows and accepts no Critic, Reviser, or Judge payloads.
    """
    story_setting = "\n\n".join(filter(None, [
        _section("Project", "\n".join(filter(None, [
            f"Name: {writer_context.get('project_name', '')}".rstrip(),
            f"Genre: {writer_context.get('project_genre', '')}".rstrip(),
            f"Default POV: {writer_context.get('default_pov', '')}".rstrip(),
            f"Author note: {writer_context.get('author_note', '')}".rstrip(),
        ]))),
        _section("Project documents", writer_context.get("project_documents", "")),
        _section("Novel mode boundary", NOVEL_MODE_CONTEXT),
    ]))

    planner_reference = (
        f"Selected Planner Candidate ID: {selected_planner_candidate_id}"
        if selected_planner_candidate_id else ""
    )
    peip = "\n\n".join(filter(None, [
        _section("Selected Planner output", "\n".join(filter(None, [
            planner_reference,
            str(writer_context.get("scene_plan", "")).strip(),
        ]))),
        _section("User instruction", writer_context.get("scene_instruction", "")),
        _section("Writer run override", writer_context.get("run_override", "")),
    ]))

    variables = adapt_project_variables(
        project_documents=story_setting,
        recent_chapters=str(writer_context.get("recent_chapters", "") or ""),
        current_chapter_text=str(writer_context.get("current_chapter_text", "") or ""),
        previous_writer_output=str(writer_context.get("continuation_anchor", "") or ""),
        scene_instruction=peip,
    )
    return TGBreakProjectData(
        variables=variables,
        selected_planner_candidate_id=selected_planner_candidate_id,
    )
