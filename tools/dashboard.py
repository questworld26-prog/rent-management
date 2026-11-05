"""CLI entrypoint for running the NiceGUI Executive Dashboard."""

import argparse
import sys
from pathlib import Path

from nicegui import ui

from src.ui.app import create_app


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="dashboard",
        description="Run local-first NiceGUI Executive Rental Management Dashboard",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to project config file (default: config.toml)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",  # noqa: S104 - Intentionally allowing 0.0.0.0 for local LAN/Wi-Fi dashboard access
        help="Host address to bind dashboard (default: 0.0.0.0 for LAN & Wi-Fi access)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Local port to serve the dashboard on (default: 8080)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open browser window upon server launch",
    )

    args = parser.parse_args()

    try:
        create_app(args.config)
        if args.host == "0.0.0.0":  # noqa: S104
            print(
                f"\n🚀 Launching Rent Management Dashboard on http://localhost:{args.port} (and LAN on port {args.port})..."
            )
        else:
            print(f"\n🚀 Launching Rent Management Dashboard on http://{args.host}:{args.port}...")
        ui.run(
            title="Rent Management Executive Dashboard",
            host=args.host,
            port=args.port,
            reload=False,
            show=not args.no_browser,
            dark=True,
        )
        return 0
    except Exception as exc:
        print(f"❌ Error starting dashboard: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
