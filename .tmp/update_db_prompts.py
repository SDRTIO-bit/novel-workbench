import sqlite3
import sys
sys.path.insert(0, '.')
from app.prompts.defaults import BUILTIN_PROMPTS

conn = sqlite3.connect('../../data/novel_workbench.db')

for entry in BUILTIN_PROMPTS:
    stage = entry['stage']
    
    # Find the latest version for this stage's builtin profile
    row = conn.execute('''
        SELECT pv.id, pv.version_number 
        FROM prompt_versions pv 
        JOIN prompt_profiles pp ON pv.profile_id = pp.id 
        WHERE pp.stage = ? AND pp.is_builtin = 1
        ORDER BY pv.version_number DESC 
        LIMIT 1
    ''', (stage,)).fetchone()
    
    if row:
        version_id, version_num = row
        conn.execute('''
            UPDATE prompt_versions 
            SET system_template = ?, user_template = ?, output_mode = ?, output_schema_name = ?
            WHERE id = ?
        ''', (
            entry['system_template'],
            entry['user_template'],
            entry['output_mode'],
            entry['output_schema_name'],
            version_id
        ))
        print(f"Updated {stage} v{version_num} (id={version_id[:8]}...)")
        print(f"  system_template: {len(entry['system_template'])} chars")
    else:
        print(f"No builtin profile found for {stage}")

conn.commit()
conn.close()
print("\nDone! All prompts updated in DB.")
