import sqlite3

db_path = r"E:\3\novel-workbench\__evaluation\sacrificial_preflight_fusion_v9_feasibility_v1_NM-03.sqlite3"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== V9 Projects ===")
cursor.execute("SELECT id, name, genre, created_at FROM projects WHERE name LIKE '%SACRIFICIAL_PREFLIGHT_FUSION_V9%'")
for row in cursor.fetchall():
    print(row)

print("\n=== V9 Chapters ===")
cursor.execute("""
SELECT c.id, c.project_id, c.title, c.sort_order 
FROM chapters c 
JOIN projects p ON c.project_id = p.id 
WHERE p.name LIKE '%SACRIFICIAL_PREFLIGHT_FUSION_V9%'
""")
for row in cursor.fetchall():
    print(row)

print("\n=== V9 Generation Runs ===")
cursor.execute("""
SELECT r.id, r.project_id, r.chapter_id, r.scene_instruction 
FROM generation_runs r 
JOIN projects p ON r.project_id = p.id 
WHERE p.name LIKE '%SACRIFICIAL_PREFLIGHT_FUSION_V9%'
""")
for row in cursor.fetchall():
    print(row[0], row[1], row[2], (row[3] or '')[:100])

conn.close()
