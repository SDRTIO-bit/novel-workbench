# Novel Workbench Evaluation MCP

This is a separate external-review server. It never imports the application
database and never exposes any operation that changes a Prompt, Candidate,
Run, or final composition.

Run it from the repository root:

```powershell
$env:PYTHONPATH = 'apps/api;.'
python -m tools.novel_eval_mcp.server
```

It reads only `__evaluation/cases_manifest.json` and the case JSON packages.
Its sole write is a schema-validated JSON result under `__evaluation/results/`.

For a new frozen batch, use:

```powershell
$env:NW_DATA_DIR = 'E:\3\novel-workbench\data'
python scripts/run_generalization_batch.py --database 'E:\3\novel-workbench\.local\experiments\planner-builtin-writer-d.db'
```

The runner records any stage failure and stops that case. Do not rerun a
failed case as part of the same frozen batch.
