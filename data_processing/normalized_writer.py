from __future__ import annotations
import math
from io import BytesIO
from typing import Any, Dict, List
import pandas as pd

def _is_nan(x: Any) -> bool:
    return isinstance(x, float) and math.isnan(x)

def _dedupe_cols(cols: List[Any]) -> List[str]:
    seen: Dict[str, int] = {}
    out: List[str] = []
    for c in cols:
        base = str(c).strip()
        if base == "" or base.lower() in ("nan", "none"):
            base = "col"
        seen[base] = seen.get(base, 0) + 1
        out.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return out

def write_normalized_workbook_data_only(
    df_raw: pd.DataFrame,
    secs_0based: List[Dict[str, Any]],
) -> bytes:
    """
    Create normalized XLSX (DATA ONLY):
      - Sheets: T1..Tn
      - FULL data rows in each section
      - Adds __src_row__ (1-based row in original input)
    Expects section keys (0-based):
      header_row, start_row, end_row, label(optional)
    """
    out = BytesIO()
    written = 0

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for i, s in enumerate(secs_0based, start=1):
            hr = int(s["header_row"])
            ds = int(s["start_row"])
            de = int(s["end_row"])

            # bounds
            if hr < 0 or ds < 0 or de < 0:
                continue
            if hr >= len(df_raw) or ds >= len(df_raw):
                continue
            if not (hr < ds <= de):
                continue
            de = min(de, len(df_raw) - 1)

            header_vals = df_raw.iloc[hr].tolist()
            header = [("" if pd.isna(x) else str(x).strip()) for x in header_vals]

            block = df_raw.iloc[ds:de + 1].copy()
            block.columns = header

            # drop empty columns
            block = block.dropna(axis=1, how="all")

            # drop columns with empty header
            keep_cols = [c for c in block.columns if str(c).strip() not in ("", "nan", "None")]
            if keep_cols:
                block = block.loc[:, keep_cols]

            if block.shape[0] == 0 or block.shape[1] == 0:
                continue

            block.columns = _dedupe_cols(list(block.columns))

            # mapping to original input rows (1-based)
            block.insert(0, "__src_row__", list(range(ds + 1, de + 2)))

            sheet_name = f"T{i}"[:31]
            block.to_excel(writer, sheet_name=sheet_name, index=False)
            written += 1

    if written == 0:
        raise ValueError("No valid tables to write. Please adjust sections and confirm again.")

    return out.getvalue()
