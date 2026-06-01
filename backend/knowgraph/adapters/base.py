from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd


def safe_str(val: object, default: str = "") -> str:
    if pd.isna(val):
        return default
    return str(val)


def safe_int(val: object, default: int = 0) -> int:
    if pd.isna(val):
        return default
    return int(val)  # type: ignore


class BaseAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def row_to_dict(self, row: dict) -> dict:
        ...

    def validate_row(self, row: dict) -> bool:
        return True

    def load_csv(self, path: str | Path) -> list[dict]:
        path = Path(path)
        df = pd.read_csv(path)
        result: list[dict] = []
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            if not self.validate_row(row_dict):
                continue
            converted = self.row_to_dict(row_dict)
            result.append(converted)
        return result
