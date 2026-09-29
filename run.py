#!/usr/bin/env python3
"""
ResearchIQ launcher — auto-activates the .venv if needed.
Run from the project root:  python run.py
"""
import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
_venv_dir = ROOT / ".venv"

# Re-exec under the venv Python if we're not already running inside it.
# We check sys.prefix rather than sys.executable because the venv Python
# symlink may resolve to the same binary as the system Python.
if _venv_dir.exists() and Path(sys.prefix).resolve() != _venv_dir.resolve():
    _venv_python = _venv_dir / "bin" / "python"
    if _venv_python.exists():
        os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)

sys.path.insert(0, str(ROOT))

try:
    import uvicorn
except ModuleNotFoundError:
    print("\n  ERROR: Dependencies not installed.")
    print("  Run setup first:\n")
    print(f"    cd \"{ROOT}\"")
    print("    ./setup.sh")
    print("\n  Then:  python run.py\n")
    sys.exit(1)

if __name__ == "__main__":
    print("\n  ResearchIQ starting…  →  http://localhost:8000\n")
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["backend", "frontend"],
    )
