"""Console entrypoint: launch the WakaFlockaFlow server (API + bundled SPA).

Installed as the ``wakaflockaflow`` command. The backend modules use flat
top-level imports (``import main``, ``import models_cluster``), so the launcher
puts this package's directory on ``sys.path`` before starting uvicorn. It points
the bundled frontend and demo data at the packaged copies and writes runtime
state to a user-writable directory (never site-packages).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> None:
    pkg = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(
        prog="wakaflockaflow",
        description="Launch WakaFlockaFlow (browser UI + API) on your machine.",
    )
    parser.add_argument("--host", default=os.environ.get("WAKAFLOCKA_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("WAKAFLOCKA_PORT", "8000")))
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("WAKAFLOCKA_DATA", str(Path.cwd() / "wakaflockaflow-data")),
        help="where to store the database, uploads and exports (default: ./wakaflockaflow-data)",
    )
    args = parser.parse_args()

    # Flat module imports (main, models_cluster, ...) resolve from the package dir.
    sys.path.insert(0, str(pkg))

    webui = pkg / "webui"
    if webui.is_dir():
        os.environ.setdefault("WAKAFLOCKA_STATIC", str(webui))
    sample = pkg / "sample_data"
    if sample.is_dir():
        os.environ.setdefault("WAKAFLOCKA_SAMPLE_DATA", str(sample))
    os.environ["WAKAFLOCKA_DATA"] = args.data_dir

    import uvicorn

    print(
        f"WakaFlockaFlow: http://{args.host}:{args.port}\n"
        f"  data dir: {args.data_dir}\n"
        f"  UI bundle: {'packaged' if webui.is_dir() else 'not bundled (API only)'}"
    )
    uvicorn.run("main:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
