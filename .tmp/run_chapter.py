import asyncio
import json
import os
import subprocess
import sys
import time
import httpx

API_DIR = r"E:\3\novel-workbench\apps\api"
DATA_DIR = r"E:\3\novel-workbench\data"
PYTHON = r"E:\3\novel-workbench\apps\api\venv\Scripts\python.exe"
BASE_URL = "http://127.0.0.1:8766"


def start_server():
    env = {
        **dict(subprocess.os.environ),
        "DATA_DIR": DATA_DIR,
        "PYTHONPATH": API_DIR,
    }
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    stdout_path = os.path.join(log_dir, "server_stdout.log")
    stderr_path = os.path.join(log_dir, "server_stderr.log")
    stdout_f = open(stdout_path, "w", encoding="utf-8")
    stderr_f = open(stderr_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8766"],
        cwd=API_DIR,
        env=env,
        stdout=stdout_f,
        stderr=stderr_f,
    )
    proc._stdout_f = stdout_f
    proc._stderr_f = stderr_f
    return proc


async def wait_for_server(client: httpx.AsyncClient, timeout: float = 60.0):
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
        async with httpx.AsyncClient(timeout=60.0) as client:
            await wait_for_server(client)
            print("[1/13] 后端 API 已启动")

            # 1. 创建项目
            r = await client.post(
                f"{BASE_URL}/api/projects",
                json={"name": "《黄昏书屋》", "genre": "温情现实主义", "author_note": "", "default_pov": "第三人称"},
            )
            r.raise_for_status()
            project = r.json()
            project_id = project["id"]
            print(f"[2/13] 创建项目: {project['name']} ({project_id[:8]})")

            # 2. 设置项目资料
            docs = {
                "summary": {"title": "梗概", "content": "退休旧书店老板老陈在黄昏时遇到迷路女孩小满，一段关于信任与陪伴的故事。"},
                "outline": {"title": "大纲", "content": "第一章：相遇；第二章：熟悉；第三章：告别与约定。"},
                "characters": {"title": "人物", "content": "老陈：寡言、温和、守旧书店；小满：六岁、敏感、刚上小学；阿橘：书店的橘猫。"},
                "world": {"title": "世界观", "content": "南方老城，梧桐老街，旧书店，黄昏光线。"},
                "style": {"title": "风格", "content": "克制、细节化、留白、通过动作和环境传递情感。"},
                "principles": {"title": "原则", "content": "不煽情，不用巧合解决冲突，用具体动作代替心理标签。"},
            }
            for kind, data in docs.items():
                r = await client.put(
                    f"{BASE_URL}/api/projects/{project_id}/documents/{kind}",
                    json=data,
                )
                r.raise_for_status()
            print("[3/13] 已写入项目资料")

            # 3. 创建章节
            r = await client.post(
                f"{BASE_URL}/api/projects/{project_id}/chapters",
                json={"title": "第一章：铜铃响了", "sort_order": 0, "current_text": ""},
            )
            r.raise_for_status()
            chapter = r.json()
            chapter_id = chapter["id"]
            print(f"[4/13] 创建章节: {chapter['title']} ({chapter_id[:8]})")

            # 4. 获取默认工作流
            r = await client.get(f"{BASE_URL}/api/workflows")
            r.raise_for_status()
            workflows = r.json()
            default_wf = next((w for w in workflows if w.get("is_default")), workflows[0])
            workflow_id = default_wf["id"]
            print(f"[5/13] 使用工作流: {default_wf['name']} ({workflow_id[:8]})")

            # 5. 创建运行
            r = await client.post(
                f"{BASE_URL}/api/runs",
                json={
                    "project_id": project_id,
                    "chapter_id": chapter_id,
                    "workflow_profile_id": workflow_id,
                    "scene_instruction": "老陈在黄昏的书店里，准备关门时，门口出现一个红着眼眶的小女孩。",
                },
            )
            r.raise_for_status()
            run = r.json()
            run_id = run["id"]
            print(f"[6/13] 创建运行: {run_id[:8]}")

            async def execute_and_select(stage: str):
                print(f"    开始执行 {stage} ...")
                r = await client.post(
                    f"{BASE_URL}/api/runs/{run_id}/steps/{stage}/execute",
                    json={},
                    timeout=120.0,
                )
                r.raise_for_status()
                candidate = r.json()
                if candidate.get("error_code"):
                    raise RuntimeError(f"{stage} 执行失败: {candidate['error_code']} - {candidate['error_message']}")
                cand_id = candidate["id"]
                r = await client.post(
                    f"{BASE_URL}/api/runs/{run_id}/steps/{stage}/select/{cand_id}",
                    json={},
                )
                r.raise_for_status()
                print(f"[OK] {stage} 完成，候选 {cand_id[:8]}")
                return candidate

            # 6. Planner
            planner = await execute_and_select("planner")
            planner_data = json.loads(planner["parsed_output_json"])
            print(f"    场景目标: {planner_data['scene_goal']}")
            print(f"    地点: {planner_data['location']}")
            print(f"    人物: {', '.join(c['name'] for c in planner_data['characters'])}")

            # 7. Writer
            writer = await execute_and_select("writer")
            draft_text = writer["text_output"]
            print(f"    初稿字数: {len(draft_text)}")

            # 8. Critic
            critic = await execute_and_select("critic")
            critic_data = json.loads(critic["parsed_output_json"])
            issues = critic_data.get("issues", [])
            print(f"    诊断问题数: {len(issues)}")

            # 9. 选择要修复的问题
            if issues:
                issue_ids = [issue["issue_id"] for issue in issues[:3]]
                operation_by_issue = {
                    issue["issue_id"]: issue["recommended_operation"]
                    for issue in issues[:3]
                }
                r = await client.post(
                    f"{BASE_URL}/api/runs/{run_id}/critic/select-issues",
                    json={"issue_ids": issue_ids, "operation_by_issue": operation_by_issue},
                )
                r.raise_for_status()
                print(f"    选择修复: {', '.join(issue_ids)}")
            else:
                issue_ids = []

            # 10. Reviser
            reviser = await execute_and_select("reviser")
            reviser_data = json.loads(reviser["parsed_output_json"])
            revised_text = reviser_data.get("revised_text", "")
            print(f"    修订稿字数: {len(revised_text)}")

            # 11. Judge
            judge = await execute_and_select("judge")
            judge_data = json.loads(judge["parsed_output_json"])
            print(f"    审稿决定: {judge_data['decision']}")
            print(f"    质量评分: {judge_data.get('quality_score', 'N/A')}")

            # 12. 采用最终文本
            accept_type = "judge"
            r = await client.post(
                f"{BASE_URL}/api/runs/{run_id}/accept",
                json={"accept_type": accept_type, "final_text": None},
            )
            r.raise_for_status()
            accept_result = r.json()
            print(f"[7/13] 已采用文本: {accept_result}")

            # 13. 获取最终章节（通过版本获取）
            r = await client.get(f"{BASE_URL}/api/chapters/{chapter_id}/versions")
            r.raise_for_status()
            versions = r.json()
            if versions:
                latest_version = max(versions, key=lambda v: v["version_number"])
                final_text = latest_version["text"]
                print(f"[8/13] 章节当前字数: {len(final_text)}")
                print(f"[9/13] 章节版本: v{latest_version['version_number']}")

                print("\n" + "=" * 60)
                print("最终章节文本")
                print("=" * 60)
                print(final_text)
                print("=" * 60)
            else:
                print("[8/13] 未找到章节版本")

            print(f"\n[10/13] 章节版本数: {len(versions)}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        proc._stdout_f.close()
        proc._stderr_f.close()
        print("\n[11/13] 后端 API 已停止")


if __name__ == "__main__":
    asyncio.run(main())
