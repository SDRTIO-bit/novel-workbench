# DETECTOR_GENERALIZATION_V2 manual submission set

`zhuque_submission_all.txt` contains all 72 generated novel passages in shuffled order, without group labels or sample identifiers. It is the file to paste into the external detector. Five blank-line separators mark original text boundaries, but the detector may split across them; that is expected.

`blind_texts/` holds the same passages separately for optional one-by-one checking. Keep `source_mapping.private.json` hidden until detector notes and human blind-review notes have been recorded. Fifteen passages carry a mechanical final-line validation mismatch in the private mapping; their generated text is intentionally retained because this experiment forbids retry/selection.
