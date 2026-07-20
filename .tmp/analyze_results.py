import json
d = json.load(open(r"E:\3\novel-workbench\__evaluation\sacrificial_preflight_feasibility_v1\validation_summary.json", "r", encoding="utf-8"))
drafts = d["drafts"]

print("=== Per-group text character counts ===")
print()

print("Group A (v6 plain_text):")
a = [x for x in drafts if x["group"] == "A"]
for x in sorted(a, key=lambda x: (x["case_id"], x["replica"])):
    print(f"  {x['case_id']}-{x['replica']}: text={x['text_character_count']}")
a_t = [x["text_character_count"] for x in a]
print(f"  avg: {sum(a_t)/len(a_t):.0f}  min: {min(a_t)}  max: {max(a_t)}")

print()
print("Group P (v7 xml_story):")
p = [x for x in drafts if x["group"] == "P"]
for x in sorted(p, key=lambda x: (x["case_id"], x["replica"])):
    print(f"  {x['case_id']}-{x['replica']}: story={x['text_character_count']} dn={x['draft_notes_character_count']}")
p_t = [x["text_character_count"] for x in p]
p_dn = [x["draft_notes_character_count"] for x in p]
print(f"  story avg: {sum(p_t)/len(p_t):.0f}  min: {min(p_t)}  max: {max(p_t)}")
print(f"  draft_notes avg: {sum(p_dn)/len(p_dn):.0f}  min: {min(p_dn)}  max: {max(p_dn)}")

print()
s = [x for x in drafts if x.get("text_length_shortfall")]
print(f"Text length shortfall (<1800 chars): {len(s)}/24")

# Error codes
errs = [x for x in drafts if x.get("error_code")]
print(f"Errors: {len(errs)}/24")
for x in errs:
    print(f"  {x['case_id']}-{x['group']}-{x['replica']}: {x['error_code']}")
