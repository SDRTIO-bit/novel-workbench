import sqlite3
import json

db_path = r"E:\3\novel-workbench\__evaluation\sacrificial_preflight_fusion_v9_feasibility_v1_NM-03.sqlite3"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== Tables ===")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
for row in cursor.fetchall():
    print(row[0])

print("\n=== Projects ===")
cursor.execute("SELECT id, name, genre FROM projects")
for row in cursor.fetchall():
    print(row)

print("\n=== Chapters ===")
cursor.execute("SELECT id, project_id, title, sort_order FROM chapters")
for row in cursor.fetchall():
    print(row)

print("\n=== Generation Runs ===")
cursor.execute("SELECT id, project_id, chapter_id, scene_instruction FROM generation_runs")
for row in cursor.fetchall():
    print(row[0], row[1], row[2], (row[3] or "")[:80])

print("\n=== Generation Steps ===")
cursor.execute("SELECT id, run_id, stage, status FROM generation_steps")
for row in cursor.fetchall():
    print(row)

print("\n=== Generation Candidates (planner) ===")
cursor.execute("""
SELECT c.id, c.step_id, c.attempt_number, c.parsed_output_json, c.text_output 
FROM generation_candidates c 
JOIN generation_steps s ON c.step_id = s.id 
WHERE s.stage = 'planner'
""")
for row in cursor.fetchall():
    parsed = json.loads(row[3]) if row[3] else {}
    print(f"Candidate {row[0]}: step={row[1]}, attempt={row[2]}, has_parsed={bool(parsed)}")
    if parsed:
        print(f"  scene_goal={parsed.get('scene_goal','')[:50]}")

conn.close()
