import csv
from pathlib import Path

import pandas as pd


def rows_from_file(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path).fillna("").to_dict(orient="records")
    raise ValueError("Structured ingestion supports CSV and Excel")
