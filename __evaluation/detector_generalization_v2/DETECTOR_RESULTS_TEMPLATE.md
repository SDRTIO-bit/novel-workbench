# DETECTOR_GENERALIZATION_V2 results

For every blind ID in `blind_review_queue.json`, record the external detector's three character ratios, each orange span (start/end paragraph or character offset), and the largest continuous orange length. Do not alter draft text or group mappings. External segmentation can cross draft boundaries, so preserve the source mapping before assigning any per-draft values.

Decision gates: B or C median human ratio ≥ 60%; at least 8 of 12 scenarios better than A; blind human review not below A; and no increase in Planner-external facts.
