"""Automated reliability smoke tests for fierry-mare bot.

Usage:
  python ops_test_suite.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run(name: str, command: list[str]) -> None:
    print(f"[TEST] {name}")
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        print(f"[FAIL] {name}")
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        raise SystemExit(1)

    print(f"[OK] {name}")


def main() -> None:
    py = sys.executable
    run(
        "Compile core modules",
        [
            py,
            "-m",
            "py_compile",
            "submission_bot.py",
            "src/whatsapp_service.py",
            "src/config.py",
        ],
    )
    run("Unit tests", [py, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run(
        "Runtime strict target check",
        [
            py,
            "-c",
            "from src.config import Config; c=Config(); assert c.targets=={'Ibrahim':'+923300301917','Muazzam':'+923055375994'}; print('strict-targets-ok')",
        ],
    )
    run(
        "Journal restart duplicate-prevention check",
        [
            py,
            "-c",
            (
                "import os,tempfile,submission_bot as sb; "
                "p=os.path.join(tempfile.gettempdir(),'journal_restart_test.json'); "
                "rows={}; rid='ts|X|Y'; sb._journal_mark_target(rows,rid,'Ibrahim'); "
                "sb._journal_save(p,rows); rows2=sb._journal_load(p); "
                "delivered=sb._journal_targets(rows2,rid); "
                "assert 'Ibrahim' in delivered and 'Muazzam' not in delivered; "
                "os.remove(p); print('journal-restart-ok')"
            ),
        ],
    )
    run(
        "Brave Selenium startup probe (temp profile)",
        [
            py,
            "-c",
            (
                "from selenium import webdriver; import tempfile; "
                "p=r'C:\\\\Users\\\\hafiz\\\\AppData\\\\Local\\\\BraveSoftware\\\\Brave-Browser\\\\Application\\\\brave.exe'; "
                "d=tempfile.mkdtemp(prefix='wa_probe_'); "
                "o=webdriver.ChromeOptions(); o.binary_location=p; "
                "o.add_argument('--user-data-dir='+d); o.add_argument('--disable-gpu'); "
                "o.add_argument('--no-sandbox'); o.add_argument('--disable-dev-shm-usage'); "
                "drv=webdriver.Chrome(options=o); drv.get('https://web.whatsapp.com'); drv.quit(); "
                "print('brave-probe-ok')"
            ),
        ],
    )
    run(
        "Structured telemetry helpers check",
        [
            py,
            "-c",
            (
                "import os,tempfile,submission_bot as sb; "
                "d=tempfile.mkdtemp(prefix='hb_'); "
                "hb=os.path.join(d,'h.json'); ev=os.path.join(d,'e.jsonl'); "
                "stats=sb.RunStats(startup_time=0.0); "
                "sb._write_heartbeat(hb,123,stats,last_error=''); "
                "sb._append_event(ev,'ok',k='v'); "
                "assert os.path.exists(hb) and os.path.exists(ev); print('telemetry-ok')"
            ),
        ],
    )
    print("\nAll automated reliability tests passed.")


if __name__ == "__main__":
    main()
