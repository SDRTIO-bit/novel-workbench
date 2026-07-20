"""Phase 3 evidence verification (read-only)."""
import json
import sqlite3
from pathlib import Path

root = Path(r"E:\3\novel-workbench\__evaluation\narrative_permission_stopping_factorial_v1")

all_ok = True
for case_id in ("AL-01", "NM-03"):
    case = json.loads((root / "cases" / case_id / "result.json").read_text(encoding="utf-8"))
    run_id = case["run_id"]
    db = root.parent / f"{root.name}_{case_id}.sqlite3"
    con = sqlite3.connect(db)
    rows = con.execute(
        """
        SELECT gc.attempt_number, gc.parameters_json, substr(gc.rendered_user_prompt, -1200)
        FROM generation_candidates gc
        JOIN generation_steps gs ON gc.step_id = gs.id
        WHERE gs.stage = 'writer' AND gs.run_id = ?
        ORDER BY gc.attempt_number
        """,
        (run_id,),
    ).fetchall()
    con.close()
    print("=" * 15, case_id, "run", run_id[:8], "| writer candidates:", len(rows))
    for attempt, params, tail in rows:
        p = json.loads(params)
        meta = p.get("policy_metadata") or {}
        group = meta.get("group")
        has_limited = "叙述权限" in tail
        has_stop = "停止纪律" in tail
        ok = (
            (group == "A" and not has_limited and not has_stop)
            or (group == "B" and has_limited and not has_stop)
            or (group == "C" and not has_limited and has_stop)
            or (group == "D" and has_limited and has_stop)
        )
        all_ok = all_ok and ok
        print(
            f"  attempt {attempt:2d} group={group} "
            f"policies={meta.get('permission_policy')}+{meta.get('stop_policy')} "
            f"seed={meta.get('seed')} ih={(meta.get('instruction_hash') or 'None')[:12]} "
            f"| 叙述权限={has_limited} 停止纪律={has_stop} | match={ok}"
        )

print()
print("ALL GROUP/PROMPT MATCHES:", all_ok)

# Planner calls: one per case
for case_id in ("AL-01", "NM-03"):
    case = json.loads((root / "cases" / case_id / "result.json").read_text(encoding="utf-8"))
    run_id = case["run_id"]
    db = root.parent / f"{root.name}_{case_id}.sqlite3"
    con = sqlite3.connect(db)
    n = con.execute(
        """
        SELECT count(*) FROM generation_candidates gc
        JOIN generation_steps gs ON gc.step_id = gs.id
        WHERE gs.stage = 'planner' AND gs.run_id = ?
        """,
        (run_id,),
    ).fetchone()[0]
    con.close()
    print(f"{case_id}: planner candidates = {n} (expect 1)")

# Validator summary spot check
vs = json.loads((root / "validation_summary.json").read_text(encoding="utf-8"))
drafts = vs["drafts"]
print("validation rows:", len(drafts))
from collections import Counter

code_counter = Counter()
for d in drafts:
    for c in d["validator_codes"]:
        code_counter[c] += 1
print("validator code totals:", dict(code_counter))
tempo_by_group = Counter(d["group"] for d in drafts if d["tempo_final_line_mismatch"])
print("TEMPO mismatches by group:", dict(tempo_by_group))
char_stats = {}
for g in ("A", "B", "C", "D"):
    counts = [d["character_count"] for d in drafts if d["group"] == g]
    char_stats[g] = (min(counts), round(sum(counts) / len(counts)), max(counts))
print("char count (min/avg/max) by group:", char_stats)
