# services/io_readers.py
import os
import pandas as pd

def read_df_any(file_path: str) -> pd.DataFrame:
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext in [".xlsx", ".xls"]:
        return pd.read_excel(file_path, header=None)
    if ext in [".csv"]:
        return pd.read_csv(file_path, header=None)
    # nếu bạn có pdf pipeline riêng thì để sau
    raise ValueError(f"Unsupported file type: {ext}")
