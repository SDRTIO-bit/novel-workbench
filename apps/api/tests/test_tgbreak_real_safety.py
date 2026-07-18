import subprocess
from pathlib import Path


def test_local_preset_path_is_git_ignored():
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "check-ignore", "-v", "--", ".local/safety-probe.json"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert ".local/" in result.stdout
