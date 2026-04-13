from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.config.settings import get_settings
from app.infrastructure.database.mongodb import MongoDB


async def _load_industries() -> list[dict[str, int | str | None]]:
    settings = get_settings()
    await MongoDB.connect(settings.MONGODB_URI, settings.MONGODB_DB_NAME)
    try:
        collection = MongoDB.get_db().stock_symbols
        pipeline = [
            {
                "$match": {
                    "industry_code": {"$ne": None},
                    "industry_name": {"$ne": None},
                }
            },
            {
                "$group": {
                    "_id": {
                        "industry_code": "$industry_code",
                        "industry_name": "$industry_name",
                    }
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "industry_code": "$_id.industry_code",
                    "industry_name": "$_id.industry_name",
                }
            },
            {"$sort": {"industry_code": 1, "industry_name": 1}},
        ]
        return [document async for document in collection.aggregate(pipeline)]
    finally:
        await MongoDB.disconnect()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List distinct industry codes and names from persisted stock catalog.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the result as JSON.",
    )
    return parser


def _print_table(rows: list[dict[str, int | str | None]]) -> None:
    if not rows:
        print("No industry data found in stock_symbols.")
        return

    code_width = max(len("industry_code"), *(len(str(row["industry_code"])) for row in rows))
    print(f"{'industry_code'.ljust(code_width)}  industry_name")
    print(f"{'-' * code_width}  {'-' * 32}")
    for row in rows:
        print(f"{str(row['industry_code']).ljust(code_width)}  {row['industry_name']}")


async def _main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    rows = await _load_industries()

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    _print_table(rows)


if __name__ == "__main__":
    asyncio.run(_main())
