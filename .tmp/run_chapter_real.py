import asyncio
import json
import subprocess
import time
import httpx

API_DIR = r"E:\3\novel-workbench\apps\api"
DATA_DIR = r"E:\3\novel-workbench\data"
PYTHON = r"E:\3\novel-workbench\apps\api\venv\Scripts\python.exe"
BASE_URL = "http://127.0.0.1:8766"

PROVIDER_ID = "34c14b6b-7231-432a-96b2-8272329b828d"
MODEL_ID = "deepseek-chat"
STAGES = ["planner", "writer", "critic", "reviser", "judge"]


def start_server():
    env = {
        **dict(subprocess.os.environ),
        "DATA_DIR": DATA_DIR,
        "PYTHONPATH": API_DIR,
    }
    proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8766"],
        cwd=API_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


async def wait_for_server(client, timeout=30.0):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = await client.get(f"{BASE_URL}/api/health", timeout=2.0)
            if r.status_code == 200:
                return
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError("Server did not start in time")


async def main():
    proc = start_server()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            await wait_for_server(client)
            print("[1] 后端 API 已启动")

            # 获取默认工作流并切换到真实模型
            r = await client.get(f"{BASE_URL}/api/workflows")
            r.raise_for_status()
            workflows = r.json()
            default_wf = next(w for w in workflows if w.get("is_default"))
            workflow_id = default_wf["id"]

            for stage in STAGES:
                r = await client.put(
                    f"{BASE_URL}/api/workflows/{workflow_id}/steps/{stage}",
                    json={"provider_id": PROVIDER_ID, "model_id": MODEL_ID},
                )
                r.raise_for_status()
            print(f"[2] 工作流已切换到 {MODEL_ID}")

            # 创建项目
            r = await client.post(
                f"{BASE_URL}/api/projects",
                json={"name": "黄昏书屋", "genre": "温情现实主义", "author_note": "", "default_pov": "第三人称有限"},
            )
            r.raise_for_status()
            project = r.json()
            project_id = project["id"]
            print(f"[3] 创建项目: {project['name']}")

            # 写入项目资料
            docs = {
                "summary": "退休旧书店老板老陈在黄昏时遇到迷路女孩小满，一段关于信任与陪伴的故事。",
                "outline": "第一章：相遇——老陈在书店关门时遇到迷路的小满，通过安静的动作建立初步信任。",
                "characters": "老陈：六十多岁，寡言温和，守着亡妻留下的旧书店，不善表达但内心细腻。小满：六岁，敏感，刚上小学，放学后走散。阿橘：书店的橘猫，每天黄昏准时在窗台。",
                "world": "南方老城梧桐老街，旧书店'时光书屋'，木质书架，铜铃门铃，黄昏光线。",
                "style": "克制、细节化、留白。通过动作和感官细节传递情感，不用心理标签，不煽情。",
                "principles": "不煽情，不用巧合解决冲突，用具体动作代替心理描写，展示而非说教。",
            }
            for kind, content in docs.items():
                r = await client.put(
                    f"{BASE_URL}/api/projects/{project_id}/documents/{kind}",
                    json={"title": kind, "content": content},
                )
                r.raise_for_status()
            print("[4] 已写入项目资料")

            # 创建章节
            r = await client.post(
                f"{BASE_URL}/api/projects/{project_id}/chapters",
                json={"title": "第一章：铜铃响了", "sort_order": 0, "current_text": ""},
            )
            r.raise_for_status()
            chapter = r.json()
            chapter_id = chapter["id"]
            print(f"[5] 创建章节: {chapter['title']}")

            # 创建运行
            r = await client.post(
                f"{BASE_URL}/api/runs",
                json={
                    "project_id": project_id,
                    "chapter_id": chapter_id,
                    "workflow_profile_id": workflow_id,
                    "scene_instruction": "老陈在黄昏的书店里准备关门，门口出现一个红着眼眶、攥着书包带子的小女孩。通过递水、橘猫阿橘的互动等安静的动作建立初步信任。",
                },
            )
            r.raise_for_status()
            run = r.json()
            run_id = run["id"]
            print(f"[6] 创建运行: {run_id[:8]}")

            async def execute_and_select(stage, max_retries=3):
                for attempt in range(1, max_retries + 1):
                    print(f"    执行 {stage} (尝试 {attempt})...", end="", flush=True)
                    r = await client.post(
                        f"{BASE_URL}/api/runs/{run_id}/steps/{stage}/execute",
                        json={},
                    )
                    r.raise_for_status()
                    candidate = r.json()
                    if candidate.get("error_code") == "LLM_RATE_LIMIT" and attempt < max_retries:
                        wait = attempt * 15
                        print(f" 限流，等待 {wait}s...")
                        await asyncio.sleep(wait)
                        continue
                    if candidate.get("error_code"):
                        print(f" 失败: {candidate['error_code']}")
                        print(f"    {candidate.get('error_message', '')[:200]}")
                        raise RuntimeError(f"{stage} failed: {candidate['error_code']}")
                    cand_id = candidate["id"]
                    r = await client.post(
                        f"{BASE_URL}/api/runs/{run_id}/steps/{stage}/select/{cand_id}",
                        json={},
                    )
                    r.raise_for_status()
                    latency = candidate.get("latency_ms", "?")
                    tokens = candidate.get("output_tokens", "?")
                    print(f" 完成 ({latency}ms, {tokens} tokens)")
                    return candidate
                raise RuntimeError(f"{stage} exhausted retries")

            # Planner
            planner = await execute_and_select("planner")
            planner_data = json.loads(planner["parsed_output_json"])
            print(f"    场景: {planner_data['location']} / {planner_data['time']}")
            print(f"    目标: {planner_data['scene_goal']}")

            # Writer
            writer = await execute_and_select("writer")
            draft = writer["text_output"]
            print(f"    初稿: {len(draft)} 字")

            # Critic
            critic = await execute_and_select("critic")
            critic_data = json.loads(critic["parsed_output_json"])
            issues = critic_data.get("issues", [])
            print(f"    诊断: {len(issues)} 个问题")
            for issue in issues:
                print(f"      [{issue['severity']}] {issue['issue_id']}: {issue['problem'][:60]}")

            # 选择修复问题
            if issues:
                issue_ids = [i["issue_id"] for i in issues]
                op_by_issue = {i["issue_id"]: i["recommended_operation"] for i in issues}
                r = await client.post(
                    f"{BASE_URL}/api/runs/{run_id}/critic/select-issues",
                    json={"issue_ids": issue_ids, "operation_by_issue": op_by_issue},
                )
                r.raise_for_status()
                print(f"    选择修复全部 {len(issue_ids)} 个问题")

            # Reviser
            reviser = await execute_and_select("reviser")
            reviser_data = json.loads(reviser["parsed_output_json"])
            revised = reviser_data.get("revised_text", "")
            print(f"    修订稿: {len(revised)} 字")

            # Judge
            judge = await execute_and_select("judge")
            judge_data = json.loads(judge["parsed_output_json"])
            print(f"    决定: {judge_data['decision']}")
            print(f"    评分: {judge_data.get('quality_score', 'N/A')}/100")

            # 采用
            r = await client.post(
                f"{BASE_URL}/api/runs/{run_id}/accept",
                json={"accept_type": "judge", "final_text": None},
            )
            r.raise_for_status()
            print(f"[7] 已采用: {r.json()}")

            # 获取版本
            r = await client.get(f"{BASE_URL}/api/chapters/{chapter_id}/versions")
            r.raise_for_status()
            versions = r.json()
            if versions:
                latest = max(versions, key=lambda v: v["version_number"])
                print(f"\n{'='*60}")
                print(f"最终文本 (v{latest['version_number']}, {len(latest['text'])} 字)")
                print(f"{'='*60}")
                print(latest["text"])

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print(f"\n[8] 后端已停止")


if __name__ == "__main__":
    asyncio.run(main())
