import sqlite3
conn = sqlite3.connect('../../data/novel_workbench.db')

# Get the latest planner candidate with error
row = conn.execute('''
    SELECT error_code, error_message, raw_response, rendered_system_prompt 
    FROM generation_candidates 
    WHERE error_code IS NOT NULL
    ORDER BY created_at DESC 
    LIMIT 1
''').fetchone()

if row:
    print(f"Error code: {row[0]}")
    print(f"Error message: {row[1]}")
    print(f"\nRaw response (first 500 chars):")
    print(row[2][:500] if row[2] else 'None')
    print(f"\nSystem prompt (first 1000 chars):")
    print(row[3][:1000] if row[3] else 'None')
else:
    print("No error candidates found")

conn.close()
