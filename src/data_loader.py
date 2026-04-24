import pandas as pd
import numpy as np
from typing import List, Dict, Optional
import os

class DataLoader:
    def __init__(self, file_path: str, sheet_name: Optional[str] = None):
        self.file_path = file_path
        self.sheet_name = sheet_name

    @staticmethod
    def _to_str(x) -> str:
        return "" if pd.isna(x) else str(x).strip()

    @staticmethod
    def _norm(x: str) -> str:
        return "".join(str(x).lower().split())

    @staticmethod
    def _find_header_row(
        raw: pd.DataFrame, keywords: List[str], search_rows: int = 50
    ) -> Optional[int]:
        kset = set([DataLoader._norm(k) for k in keywords])
        n = min(search_rows, len(raw))
        for i in range(n):
            row = [
                DataLoader._norm(DataLoader._to_str(v))
                for v in raw.iloc[i].tolist()
            ]
            if kset.issubset(set(row)):
                return i
        return None

    @staticmethod
    def _standardize_columns(cols: List[str]) -> Dict[str, str]:
        mapping = {}
        for c in cols:
            cn = DataLoader._norm(c)
            if cn in ("time", "datetime") or ("时间" in c):
                mapping[c] = "datetime"
            elif cn == "open" or ("开盘" in c):
                mapping[c] = "open"
            elif cn == "high" or ("最高" in c):
                mapping[c] = "high"
            elif cn == "low" or ("最低" in c):
                mapping[c] = "low"
            elif cn == "close" or ("收盘" in c) or ("结算" in c):
                mapping[c] = "close"
            elif cn in ("volume", "成交量"):
                mapping[c] = "volume"
            elif cn in ("open_interest", "持仓量", "持仓"):
                mapping[c] = "open_interest"
        return mapping

    def load_data(self) -> pd.DataFrame:
        if not os.path.exists(self.file_path):
            # Try to look in data/raw
            alt_path = os.path.join("data", "raw", os.path.basename(self.file_path))
            if os.path.exists(alt_path):
                self.file_path = alt_path
            else:
                # Try to look in root if not in data/raw
                root_path = os.path.basename(self.file_path)
                if os.path.exists(root_path):
                    self.file_path = root_path
                else:
                    raise FileNotFoundError(f"Data file not found: {self.file_path}")

        print(f"Loading data from {self.file_path}...")
        if self.file_path.endswith('.xlsx'):
            raw = pd.read_excel(self.file_path, sheet_name=self.sheet_name, header=None)
        else:
            raw = pd.read_csv(self.file_path, header=None)

        if raw.empty:
            raise ValueError("Data file is empty.")

        header_row = self._find_header_row(
            raw, ["time", "close"], search_rows=50
        )

        if header_row is not None:
            header = [self._to_str(x) for x in raw.iloc[header_row].tolist()]
            data = raw.iloc[header_row + 1 :].copy()
            data.columns = header
        else:
            if self.file_path.endswith('.xlsx'):
                data = pd.read_excel(self.file_path, sheet_name=self.sheet_name)
            else:
                data = pd.read_csv(self.file_path)

        data = data.dropna(axis=1, how="all")
        col_map = self._standardize_columns(
            [self._to_str(c) for c in list(data.columns)]
        )
        data = data.rename(columns=col_map)
        
        need = {"datetime", "close"}
        missing = need - set(data.columns)
        if missing:
            raise ValueError(
                f"Missing critical columns: {sorted(missing)}; Current columns: {list(data.columns)}"
            )

        data["datetime"] = pd.to_datetime(data["datetime"], errors="coerce")
        data = data.dropna(subset=["datetime"]).sort_values("datetime")
        data = data.drop_duplicates(subset=["datetime"], keep="last")
        
        for c in ["open", "high", "low", "close", "volume", "open_interest"]:
            if c in data.columns:
                data[c] = pd.to_numeric(data[c], errors="coerce")

        print(f"Data loaded successfully. Shape: {data.shape}")
        return data.reset_index(drop=True)
