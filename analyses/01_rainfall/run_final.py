"""Run the read-only analyses and build an offline answer to both questions."""

import getpass
import os
import subprocess
import sys
from pathlib import Path

from fetch_rainfall import configuration


HERE = Path(__file__).resolve().parent


def run(label, command, environment):
    print(f"\n{label}", flush=True)
    subprocess.run(command, check=True, env=environment)


def main():
    config = configuration()
    environment = os.environ.copy()
    if not config.get("PGPASSWORD"):
        environment["PGPASSWORD"] = getpass.getpass("Database password: ")
    for name in ("analyze_temperature_rain.py", "analyze_psr.py",
                 "analyze_psr_area.py"):
        run(name, [sys.executable, str(HERE / name)], environment)
    for name, options in (("plot_temperature_rain.py", []),
                          ("plot_psr.py", []),
                          ("plot_psr.py", ["--area"])):
        run(name, ["python3", str(HERE / name), *options], environment)
    run("research_conclusions.md",
        [sys.executable, str(HERE / "report_results.py")], environment)
    print(f"\nOpen {HERE / 'results' / 'research_conclusions.md'}")


if __name__ == "__main__":
    main()
