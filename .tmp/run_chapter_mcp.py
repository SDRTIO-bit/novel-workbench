import asyncio
import json
import subprocess
import time
import sys

API_DIR = r"E:\3\novel-workbench\apps\api"
DATA_DIR = r"E:\3\novel-workbench\data"
PYTHON = r"E:\3\novel-workbench\apps\api\venv\Scripts\python.exe"
MCP_URL = "http://127.0.0.1:8766/mcp/"
MCP_TOKEN = "4B3s0uP027fytr9RB8Swu07DpI2rYn4ZIjxaUMPv6wQ"

PROVIDER_ID = "34c14b6b-7231-432a-96b2-8272329b828d"
MODEL_ID = "deepseek-v4-pro"


def start_server():
    env = {**dict(subprocess.os.environ), "DATA_DIR": DATA_DIR, "PYTHONPATH": API_DIR}
    return subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8766"],
        cwd=API_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


async def main():
    proc = start_server()
    try:
        # Wait for server
        import httpx
        async with httpx.AsyncClient() as client:
            for _ in range(40):
                try:
                    r = await client.get("http://127.0.0.1:8766/api/health", timeout=2)
                    if r.status_code == 200:
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.5)
        print("[MCP] 后端已启动")

        # Connect via MCP client
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        headers = {"Authorization": f"Bearer {MCP_TOKEN}"}

        async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("[MCP] 已连接 MCP 服务")

                # List available tools
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]
                print(f"[MCP] 可用工具: {len(tool_names)} 个")

                # 1. Create project
                result = await session.call_tool("create_project", {
                    "name": "黄昏书屋",
                    "genre": "温情现实主义",
                    "author_note": "",
                    "default_pov": "第三人称有限",
                })
                project = json.loads(result.content[0].text)
                project_id = project["id"]
                print(f"[1] 创建项目: {project['name']} ({project_id[:8]})")

                # 2. Update project documents
                docs = {
                    "summary": "退休旧书店老板老陈在黄昏时遇到迷路女孩小满，一段关于信任与陪伴的故事。",
                    "outline": "第一章：相遇——老陈在书店关门时遇到迷路的小满，通过安静的动作建立初步信任。",
                    "characters": "老陈：六十多岁，寡言温和，守着亡妻留下的旧书店。小满：六岁，敏感，放学后走散。阿橘：书店的橘猫。",
                    "world": "南方老城梧桐老街，旧书店'时光书屋'，木质书架，铜铃门铃，黄昏光线。",
                    "style": "克制、细节化、留白。通过动作和感官细节传递情感，不用心理标签，不煽情。",
                    "principles": "不煽情，不用巧合解决冲突，用具体动作代替心理描写，展示而非说教。",
                }
                for kind, content in docs.items():
                    await session.call_tool("update_project_document", {
                        "project_id": project_id,
                        "kind": kind,
                        "content": content,
                    })
                print("[2] 已写入项目资料")

                # 3. Create chapter
                result = await session.call_tool("create_chapter", {
                    "project_id": project_id,
                    "title": "第一章：铜铃响了",
                })
                chapter = json.loads(result.content[0].text)
                chapter_id = chapter["id"]
                print(f"[3] 创建章节: {chapter['title']} ({chapter_id[:8]})")

                # 4. List workflows to get default
                result = await session.call_tool("list_workflows", {})
                workflows = json.loads(result.content[0].text)
                default_wf = next(w for w in workflows if w.get("is_default"))
                workflow_id = default_wf["id"]
                print(f"[4] 默认工作流: {default_wf['name']}")

                # 5. List providers
                result = await session.call_tool("list_providers", {})
                providers = json.loads(result.content[0].text)
                for p in providers:
                    if p["provider_type"] != "mock":
                        print(f"    服务商: {p['name']} ({p['provider_type']})")
                        for m in p["models"]:
                            print(f"      - {m['model_id']}")

                # 6. Create run
                result = await session.call_tool("create_run", {
                    "project_id": project_id,
                    "chapter_id": chapter_id,
                    "workflow_profile_id": workflow_id,
                    "scene_instruction": "老陈在黄昏的书店里准备关门，门口出现一个红着眼眶、攥着书包带子的小女孩。通过递水、橘猫阿橘的互动等安静的动作建立初步信任。",
                })
                run = json.loads(result.content[0].text)
                run_id = run["id"]
                print(f"[5] 创建运行: {run_id[:8]}")

                async def execute_and_select(stage, max_retries=3, run_override=""):
                    last_error = ""
                    for attempt in range(1, max_retries + 1):
                        print(f"    执行 {stage} (尝试 {attempt})...", end="", flush=True)
                        params = {
                            "run_id": run_id,
                            "stage": stage,
                            "provider_id": PROVIDER_ID,
                            "model_id": MODEL_ID,
                        }
                        # Combine initial override with error feedback
                        override_parts = []
                        if run_override:
                            override_parts.append(run_override)
                        if last_error:
                            override_parts.append(f"上次输出错误：{last_error}。请修正。")
                        if override_parts:
                            params["run_override"] = " ".join(override_parts)
                        result = await session.call_tool("execute_stage", params)
                        candidate = json.loads(result.content[0].text)
                        if candidate.get("error_code") == "LLM_RATE_LIMIT" and attempt < max_retries:
                            wait = attempt * 15
                            print(f" 限流，等待 {wait}s...")
                            await asyncio.sleep(wait)
                            continue
                        if candidate.get("error_code"):
                            error_msg = candidate.get("error_message", candidate["error_code"])
                            print(f" 失败: {candidate['error_code']}")
                            if attempt < max_retries:
                                last_error = error_msg
                                wait = attempt * 10
                                print(f"    重试，等待 {wait}s...")
                                await asyncio.sleep(wait)
                                continue
                            raise RuntimeError(f"{stage} failed: {candidate['error_code']}")
                        cand_id = candidate["candidate_id"]
                        await session.call_tool("select_candidate", {
                            "run_id": run_id,
                            "stage": stage,
                            "candidate_id": cand_id,
                        })
                        latency = candidate.get("latency_ms", "?")
                        tokens = candidate.get("output_tokens", "?")
                        print(f" 完成 ({latency}ms, {tokens} tokens)")
                        return candidate
                    raise RuntimeError(f"{stage} exhausted retries")

                # 7. Planner
                planner = await execute_and_select("planner", run_override="重要：你的输出 JSON 必须包含字段 planner_contract_version，值必须为 2。同时必须包含 scene_state、concrete_problem、causal_transitions（至少1张，每张必须包含 consequence_would_still_happen: false）、chapter_contract_check（所有字段为 true）。")
                planner_text = planner.get("text_output", "")
                try:
                    planner_data = json.loads(planner_text)
                    print(f"    场景: {planner_data.get('location', '?')} / {planner_data.get('time', '?')}")
                    print(f"    目标: {planner_data.get('scene_goal', '?')}")
                except:
                    print(f"    规划完成")

                # 8. Writer
                writer = await execute_and_select("writer")
                draft = writer.get("text_output", "")
                print(f"    初稿: {len(draft)} 字")

                # 9. Critic
                critic = await execute_and_select("critic")
                critic_text = critic.get("text_output", "")
                try:
                    critic_data = json.loads(critic_text)
                    issues = critic_data.get("issues", [])
                    print(f"    诊断: {len(issues)} 个问题")
                    for issue in issues:
                        print(f"      [{issue.get('severity','?')}] {issue.get('issue_id','?')}: {issue.get('problem','')[:50]}")
                    if issues:
                        issue_ids = [i["issue_id"] for i in issues]
                        op_by_issue = {i["issue_id"]: i["recommended_operation"] for i in issues}
                        await session.call_tool("select_critic_issues", {
                            "run_id": run_id,
                            "issue_ids": issue_ids,
                            "operation_by_issue": json.dumps(op_by_issue, ensure_ascii=False),
                        })
                        print(f"    选择修复全部 {len(issue_ids)} 个问题")
                except Exception as e:
                    print(f"    诊断解析失败: {e}")

                # 10. Reviser
                reviser = await execute_and_select("reviser")
                reviser_text = reviser.get("text_output", "")
                try:
                    reviser_data = json.loads(reviser_text)
                    revised = reviser_data.get("revised_text", "")
                    print(f"    修订稿: {len(revised)} 字")
                except:
                    print(f"    修订完成: {len(reviser_text)} 字")

                # 11. Judge
                judge = await execute_and_select("judge")
                judge_text = judge.get("text_output", "")
                try:
                    judge_data = json.loads(judge_text)
                    print(f"    决定: {judge_data.get('decision', '?')}")
                    print(f"    评分: {judge_data.get('quality_score', 'N/A')}/100")
                except:
                    print(f"    评审完成")

                # 12. Accept
                result = await session.call_tool("accept_final_text", {
                    "run_id": run_id,
                    "accept_type": "judge",
                })
                accept_result = json.loads(result.content[0].text)
                print(f"[6] 已采用: {accept_result}")

                # 13. Get final chapter
                result = await session.call_tool("get_chapter", {"chapter_id": chapter_id})
                chapter = json.loads(result.content[0].text)
                final_text = chapter.get("current_text", "")

                print(f"\n{'='*60}")
                print(f"最终文本 ({len(final_text)} 字)")
                print(f"{'='*60}")
                print(final_text)

                # 14. Get versions
                result = await session.call_tool("get_chapter_versions", {"chapter_id": chapter_id})
                versions = json.loads(result.content[0].text)
                print(f"\n[7] 章节版本数: {len(versions)}")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print(f"\n[8] 后端已停止")


if __name__ == "__main__":
    asyncio.run(main())
