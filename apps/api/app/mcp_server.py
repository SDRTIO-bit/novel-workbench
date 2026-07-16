from fastmcp import FastMCP

from app.mcp_tools.project_tools import (
    list_projects,
    create_project,
    get_project,
    update_project,
    delete_project,
    restore_project,
    get_project_documents,
    update_project_document,
)
from app.mcp_tools.chapter_tools import (
    list_chapters,
    create_chapter,
    get_chapter,
    update_chapter,
    delete_chapter,
    restore_chapter,
    reorder_chapters,
    restore_chapter_version,
    get_chapter_versions,
    create_chapter_version,
)
from app.mcp_tools.generation_tools import (
    list_runs,
    create_run,
    get_run,
    execute_stage,
    select_candidate,
    select_critic_issues,
    cancel_run,
    accept_final_text,
    get_stage_status,
)
from app.mcp_tools.context_tools import (
    preview_context,
    list_workflows,
    list_providers,
    create_provider,
    create_provider_model,
    list_prompt_profiles,
)

mcp = FastMCP("novel-workbench")

mcp.tool()(list_projects)
mcp.tool()(create_project)
mcp.tool()(get_project)
mcp.tool()(update_project)
mcp.tool()(delete_project)
mcp.tool()(restore_project)
mcp.tool()(get_project_documents)
mcp.tool()(update_project_document)

mcp.tool()(list_chapters)
mcp.tool()(create_chapter)
mcp.tool()(get_chapter)
mcp.tool()(update_chapter)
mcp.tool()(delete_chapter)
mcp.tool()(restore_chapter)
mcp.tool()(reorder_chapters)
mcp.tool()(restore_chapter_version)
mcp.tool()(get_chapter_versions)
mcp.tool()(create_chapter_version)

mcp.tool()(list_runs)
mcp.tool()(create_run)
mcp.tool()(get_run)
mcp.tool()(execute_stage)
mcp.tool()(select_candidate)
mcp.tool()(select_critic_issues)
mcp.tool()(cancel_run)
mcp.tool()(accept_final_text)
mcp.tool()(get_stage_status)

mcp.tool()(preview_context)
mcp.tool()(list_workflows)
mcp.tool()(list_providers)
mcp.tool()(create_provider)
mcp.tool()(create_provider_model)
mcp.tool()(list_prompt_profiles)

mcp_http_app = mcp.http_app(path="/")
