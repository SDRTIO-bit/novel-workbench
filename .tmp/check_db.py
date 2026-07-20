import sqlite3
conn = sqlite3.connect('../../data/novel_workbench.db')
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print('Tables:', [t[0] for t in tables])

# Find the candidates table
for table in tables:
    tname = table[0]
    if 'candidate' in tname.lower() or 'output' in tname.lower():
        print(f"\nTable: {tname}")
        cols = conn.execute(f"PRAGMA table_info({tname})").fetchall()
        for col in cols:
            print(f"  {col[1]}: {col[2]}")

conn.close()
