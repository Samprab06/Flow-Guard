"""CLI: ``python -m chipignite {catalog,inventory,report}``."""
from __future__ import annotations

import argparse
import json

from .catalog import load_sources, mine_catalog
from .inventory import write_inventory
from .report import write_report


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m chipignite")
    sub = parser.add_subparsers(dest="command", required=True)
    catalog = sub.add_parser("catalog", help="mine GitHub metadata without cloning")
    catalog.add_argument("--sources", default=None)
    catalog.add_argument("--output", required=True)
    inventory = sub.add_parser("inventory", help="hash local RTL/artifact files")
    inventory.add_argument("root")
    inventory.add_argument("--output", required=True)
    report = sub.add_parser("report", help="score mined metadata JSON")
    report.add_argument("metadata")
    report.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "catalog":
        write_report(mine_catalog(load_sources(args.sources)), args.output)
    elif args.command == "inventory":
        write_inventory(args.root, args.output)
    else:
        with open(args.metadata, encoding="utf-8") as handle:
            write_report(json.load(handle), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
