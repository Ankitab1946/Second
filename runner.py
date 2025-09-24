import subprocess, os
from pathlib import Path
from app.config import load_config, ROOT

def run_pytest_and_collect():
    cfg = load_config()
    reports = cfg["reports"]

    # Always run pytest from project root and ensure PYTHONPATH includes it
    project_root = ROOT
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{str(project_root)}{os.pathsep}{env.get('PYTHONPATH','')}"

    # Ensure report folders exist (relative to project root)
    base = project_root / reports["base_dir"]; base.mkdir(parents=True, exist_ok=True)
    allure = project_root / reports["allure_dir"]; allure.mkdir(parents=True, exist_ok=True)
    html_dir = project_root / reports["html_dir"]; html_dir.mkdir(parents=True, exist_ok=True)
    ss_dir = project_root / reports["screenshots_dir"]; ss_dir.mkdir(parents=True, exist_ok=True)
    cucumber = base / "report.json"

    cmd = [
        "pytest",
        "-q",
        f"--cucumberjson={cucumber}",
        f"--alluredir={allure}",
        f"--html={html_dir/'index.html'}",
        "--self-contained-html",
    ]

    proc = subprocess.run(cmd, cwd=str(project_root), capture_output=True, text=True, env=env)

    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-10_000:],
        "stderr": proc.stderr[-10_000:],
        "cucumber": str(cucumber),
        "allure_dir": str(allure),
        "html_report": str(html_dir / "index.html"),
        "screenshots_dir": str(ss_dir),
    }
