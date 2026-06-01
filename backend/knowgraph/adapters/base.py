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
    default_csv: str = ""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)

    @abstractmethod
    def row_to_dict(self, row: dict) -> dict:
        ...

    def validate_row(self, row: dict) -> bool:
        return True

    def load_csv(self, path: str | Path | None = None) -> list[dict]:
        if path is None:
            if not self.default_csv:
                raise ValueError(f"Adapter '{self.name}' has no default_csv set")
            path = self.data_dir / self.default_csv
        else:
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
