"""Record the verified local runtime without collecting credentials or env vars."""

import hashlib
import json
import platform
import subprocess
import urllib.request
from datetime import datetime
from importlib.metadata import distributions
from pathlib import Path
from zoneinfo import ZoneInfo

root = Path(__file__).resolve().parents[1]


def command(*args):
    result = subprocess.run(args, cwd=root, text=True, capture_output=True)
    return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def get_json(endpoint):
    with urllib.request.urlopen("http://127.0.0.1:11434/api/" + endpoint, timeout=5) as response:
        return json.load(response)


snapshot = {
    "recorded_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
    "python": platform.python_version(), "machine": platform.machine(), "macos": platform.mac_ver()[0],
    "hardware": command("/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string", "hw.memsize"),
    "disk": command("df", "-h", str(root)),
    "upstream_commit": "9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9",
    "uv_lock_sha256": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
    "ollama": get_json("version"), "models": get_json("tags"),
    "loaded_models": command("/Applications/Ollama.app/Contents/Resources/ollama", "ps"),
    "packages": sorted([{"name": d.metadata["Name"], "version": d.version}
        for d in distributions()], key=lambda d: d["name"].lower()),
    "dependency_check": command(str(root / ".tools/uv/bin/uv"), "pip", "check"),
    "git_status": command("git", "status", "--short"),
}
(root / "artifacts/t1/environment.json").write_text(json.dumps(snapshot, indent=2))
print(json.dumps({"python": snapshot["python"], "macos": snapshot["macos"],
    "ollama": snapshot["ollama"], "packages": len(snapshot["packages"]),
    "dependency_check": snapshot["dependency_check"]}, indent=2))
