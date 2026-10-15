import json
import platform
import sys
from pathlib import Path

import numpy as np
import sentence_transformers
import torch


V1_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = V1_ROOT / "environment.json"


def collect_environment() -> dict:
    return {
        "os_version": platform.platform(),
        "architecture": platform.machine(),
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "device": "cpu",
        "packages": {
            "numpy": np.__version__,
            "torch": torch.__version__,
            "sentence_transformers": sentence_transformers.__version__,
        },
    }


def main() -> None:
    environment = collect_environment()
    OUTPUT_PATH.write_text(
        json.dumps(environment, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"environment={OUTPUT_PATH}")


if __name__ == "__main__":
    main()