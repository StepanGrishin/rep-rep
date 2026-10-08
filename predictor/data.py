from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import unicodedata
import re

import pandas as pd


def normalize_name(name: str) -> str:
    if not name:
        return ""

    value = unicodedata.normalize("NFKD", str(name))
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^a-zA-Z0-9 .'-]", "", value)
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def display_name(name: str) -> str:
    return " ".join(
        p.capitalize() for p in str(name).split()
    )


@dataclass(frozen=True)
class MatchRecord:
    date: pd.Timestamp
    winner: str
    loser: str
    surface: str
    tourney_level: str
    best_of: int
    winner_rank: float
    loser_rank: float
    winner_rank_points: float
    loser_rank_points: float


def _num(row, key, default=0.0):
    value = row.get(key, default)
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def load_matches(data_dir: Path) -> list[MatchRecord]:
    frames = []

    for path in sorted(data_dir.glob("atp_matches_*.csv")):
        try:
            df = pd.read_csv(path, low_memory=False)
        except Exception as exc:
            print(f"[WARN] Cannot read {path}: {exc}")
            continue

        required = {"tourney_date", "winner_name", "loser_name"}
        if not required.issubset(df.columns):
            print(f"[WARN] Skipping {path}: missing columns")
            continue

        frames.append(df)

    if not frames:
        raise FileNotFoundError(
            f"No ATP CSV files found in {data_dir}"
        )

    all_df = pd.concat(frames, ignore_index=True)
    all_df["date"] = pd.to_datetime(
        all_df["tourney_date"].astype(str),
        format="%Y%m%d",
        errors="coerce",
    )
    all_df = all_df.dropna(subset=["date"])

    records = []

    for _, row in all_df.sort_values("date").iterrows():
        winner = normalize_name(row["winner_name"])
        loser = normalize_name(row["loser_name"])

        if not winner or not loser:
            continue

        surface = str(row.get("surface", "Unknown"))
        if surface == "nan":
            surface = "Unknown"

        records.append(
            MatchRecord(
                date=row["date"],
                winner=winner,
                loser=loser,
                surface=surface,
                tourney_level=str(
                    row.get("tourney_level", "Unknown")
                ),
                best_of=int(_num(row, "best_of", 3)),
                winner_rank=_num(row, "winner_rank", 999.0),
                loser_rank=_num(row, "loser_rank", 999.0),
                winner_rank_points=_num(
                    row, "winner_rank_points", 0.0
                ),
                loser_rank_points=_num(
                    row, "loser_rank_points", 0.0
                ),
            )
        )

    return records
