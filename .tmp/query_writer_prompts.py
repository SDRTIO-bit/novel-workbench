import sqlite3
con = sqlite3.connect(r"E:\3\novel-workbench\data\novel_workbench.db")
rows = con.execute("""
    SELECT pv.id, pv.version_number, pp.name, pv.output_mode
    FROM prompt_versions pv
    JOIN prompt_profiles pp ON pv.profile_id = pp.id
    WHERE pp.stage = 'writer' AND pp.is_builtin = 1
    ORDER BY pv.version_number
""")
for r in rows.fetchall():
    print(r)
con.close()
