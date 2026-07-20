import sqlite3
conn = sqlite3.connect(r"E:\3\novel-workbench\data\novel_workbench.db")
cur = conn.cursor()
cur.execute("SELECT id, name, provider_type, encrypted_api_key IS NOT NULL as has_key FROM providers WHERE provider_type != 'mock'")
for r in cur.fetchall():
    print(r)
print("\n--- models ---")
cur.execute("SELECT provider_id, model_id, display_name, enabled FROM provider_models")
for r in cur.fetchall():
    print(r)
conn.close()
