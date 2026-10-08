import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "elo_diff",
    "surface_elo_diff",
    "elo_prob",
    "surface_elo_prob",
    "rank_diff",
    "rank_points_diff",
    "form_diff",
    "surface_form_diff",
    "matches_diff",
    "h2h",
    "common_count",
]


def make_features(snapshot):
    return {
        "elo_diff": snapshot["elo_a"] - snapshot["elo_b"],
        "surface_elo_diff": (
            snapshot["surface_elo_a"]
            - snapshot["surface_elo_b"]
        ),
        "elo_prob": snapshot["elo_prob"],
        "surface_elo_prob": snapshot["surface_elo_prob"],
        "rank_diff": snapshot["rank_b"] - snapshot["rank_a"],
        "rank_points_diff": (
            snapshot["rank_points_a"]
            - snapshot["rank_points_b"]
        ),
        "form_diff": snapshot["form_a"] - snapshot["form_b"],
        "surface_form_diff": (
            snapshot["surface_form_a"]
            - snapshot["surface_form_b"]
        ),
        "matches_diff": (
            snapshot["matches_a"] - snapshot["matches_b"]
        ),
        "h2h": snapshot["h2h"],
        "common_count": snapshot["common_count"],
    }


def dataframe(rows):
    df = pd.DataFrame(rows)

    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0

    df[FEATURE_COLUMNS] = (
        df[FEATURE_COLUMNS]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )

    return df[FEATURE_COLUMNS]
