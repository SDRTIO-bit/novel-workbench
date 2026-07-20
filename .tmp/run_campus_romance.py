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
MODEL_ID = "deepseek-chat"


def start_server():
    env = {**dict(subprocess.os.environ), "DATA_DIR": DATA_DIR, "PYTHONPATH": API_DIR}
    return subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8766"],
        cwd=API_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


async def main():
    proc = start_server()
    try:
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

        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        headers = {"Authorization": f"Bearer {MCP_TOKEN}"}

        async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("[MCP] 已连接 MCP 服务")

                # 1. Create project - 现代校园恋爱
                result = await session.call_tool("create_project", {
                    "name": "自习室的第三排",
                    "genre": "现代校园恋爱",
                    "author_note": "大学图书馆自习室里，两个考研学生从互不相注意到产生微妙联系的故事。",
                    "default_pov": "第三人称有限（苏念视角）",
                })
                project = json.loads(result.content[0].text)
                project_id = project["id"]
                print(f"[1] 创建项目: {project['name']} ({project_id[:8]})")

                # 2. Update project documents
                docs = {
                    "summary": "大三女生苏念每天下午去图书馆三楼自习室考研复习，发现隔壁座位的男生每天比她早到、比她晚走。两人从互不注意到因为一本被借走的参考书产生交集。",
                    "outline": "第一章：苏念注意到对面座位的男生又在翻同一本《高等代数》，她发现自己已经连续三天观察他。一次她去还书时，发现那本书被人借走了，而男生也刚好在找同一本书。",
                    "characters": "苏念：大三，数学系，考研目标北师大，性格内敛但观察力强，习惯用铅笔在草稿纸角落画小图案。陆行舟：大三，物理系，考研目标中科院，话少但做事细致，每天带一个保温杯。",
                    "world": "某综合性大学老图书馆三楼自习室，木质长桌，绿色台灯，窗外有银杏树。秋天，考研倒计时100天。",
                    "style": "细腻克制，通过微动作和视线描写传递情感。不写内心独白式表白，用物件和空间距离暗示心理变化。节奏舒缓但有暗流。",
                    "principles": "不用巧合推动关系，不用第三者制造冲突。情感通过空间距离变化、物件传递、视线接触来呈现。展示而非说教。",
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
                    "title": "第一章：那本书不见了",
                })
                chapter = json.loads(result.content[0].text)
                chapter_id = chapter["id"]
                print(f"[3] 创建章节: {chapter['title']} ({chapter_id[:8]})")

                # 4. List workflows
                result = await session.call_tool("list_workflows", {})
                workflows = json.loads(result.content[0].text)
                default_wf = next(w for w in workflows if w.get("is_default"))
                workflow_id = default_wf["id"]
                print(f"[4] 默认工作流: {default_wf['name']}")

                # 5. Create run
                result = await session.call_tool("create_run", {
                    "project_id": project_id,
                    "chapter_id": chapter_id,
                    "workflow_profile_id": workflow_id,
                    "scene_instruction": "苏念下午到自习室，发现对面男生已经在翻那本《高等代数》。她坐下后发现自己忘带参考书，想起昨天把那本书放回了书架但现在找不到了。男生也站起来去书架找书。两人在书架间相遇，都伸手去拿同一本被放回的书。",
                })
                run = json.loads(result.content[0].text)
                run_id = run["id"]
                print(f"[5] 创建运行: {run_id[:8]}")

                async def execute_and_select(stage, max_retries=3):
                    for attempt in range(1, max_retries + 1):
                        print(f"    执行 {stage} (尝试 {attempt})...", end="", flush=True)
                        result = await session.call_tool("execute_stage", {
                            "run_id": run_id,
                            "stage": stage,
                            "provider_id": PROVIDER_ID,
                            "model_id": MODEL_ID,
                        })
                        candidate = json.loads(result.content[0].text)
                        if candidate.get("error_code") == "LLM_RATE_LIMIT" and attempt < max_retries:
                            wait = attempt * 15
                            print(f" 限流，等待 {wait}s...")
                            await asyncio.sleep(wait)
                            continue
                        if candidate.get("error_code"):
                            print(f" 失败: {candidate['error_code']}")
                            if candidate.get("error_message"):
                                print(f"    错误详情: {candidate['error_message'][:300]}")
                            if attempt < max_retries:
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

                        # For planner, print the v2 contract details
                        if stage == "planner":
                            try:
                                planner_data = json.loads(candidate.get("text_output", "{}"))
                                print(f"    contract_version: {planner_data.get('planner_contract_version', 'N/A')}")
                                if planner_data.get('scene_state'):
                                    ss = planner_data['scene_state']
                                    print(f"    scene_state: {len(ss.get('present_characters',[]))} chars, {len(ss.get('visible_facts',[]))} facts")
                                if planner_data.get('concrete_problem'):
                                    print(f"    concrete_problem: {planner_data['concrete_problem']}")
                                cts = planner_data.get('causal_transitions', [])
                                for ct in cts:
                                    print(f"    CT {ct.get('id')}: interp={ct.get('character_interpretation','')[:30]}... rejected={ct.get('rejected_alternative','')[:30]}...")
                                    if ct.get('state_delta'):
                                        sd = ct['state_delta']
                                        print(f"      delta: {sd.get('before','')[:30]}... → {sd.get('after','')[:30]}...")
                                cc = planner_data.get('chapter_contract_check', {})
                                all_true = all(v for v in cc.values() if isinstance(v, bool))
                                print(f"    contract_check: all_true={all_true} ({len(cc)} fields)")
                            except Exception as e:
                                print(f"    (planner parse: {e})")

                        return candidate
                    raise RuntimeError(f"{stage} exhausted retries")

                # 6. Planner
                planner = await execute_and_select("planner")

                # 7. Writer
                writer = await execute_and_select("writer")
                draft = writer.get("text_output", "")
                print(f"    初稿: {len(draft)} 字")

                # 8. Critic
                critic = await execute_and_select("critic")
                critic_text = critic.get("text_output", "")
                try:
                    critic_data = json.loads(critic_text)
                    issues = critic_data.get("issues", [])
                    print(f"    诊断: {len(issues)} 个问题")
                    for issue in issues:
                        print(f"      [{issue.get('severity','?')}] {issue.get('issue_id','?')}: {issue.get('problem','')[:60]}")
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

                # 9. Reviser
                reviser = await execute_and_select("reviser")
                reviser_text = reviser.get("text_output", "")
                try:
                    reviser_data = json.loads(reviser_text)
                    revised = reviser_data.get("revised_text", "")
                    print(f"    修订稿: {len(revised)} 字")
                except:
                    print(f"    修订完成: {len(reviser_text)} 字")

                # 10. Judge
                judge = await execute_and_select("judge")
                judge_text = judge.get("text_output", "")
                try:
                    judge_data = json.loads(judge_text)
                    print(f"    决定: {judge_data.get('decision', '?')}")
                    print(f"    评分: {judge_data.get('quality_score', 'N/A')}/100")
                except:
                    print(f"    评审完成")

                # 11. Accept
                result = await session.call_tool("accept_final_text", {
                    "run_id": run_id,
                    "accept_type": "judge",
                })
                accept_result = json.loads(result.content[0].text)
                print(f"[6] 已采用: {accept_result}")

                # 12. Get final chapter
                result = await session.call_tool("get_chapter", {"chapter_id": chapter_id})
                chapter = json.loads(result.content[0].text)
                final_text = chapter.get("current_text", "")

                print(f"\n{'='*60}")
                print(f"最终文本 ({len(final_text)} 字)")
                print(f"{'='*60}")
                print(final_text)

                # 13. Get versions
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
