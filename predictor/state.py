from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from typing import Optional
import json

from .elo import EloEngine


@dataclass
class PlayerRecord:
    name: str
    wins: int = 0
    losses: int = 0
    surface_wins: dict[str, int] = field(default_factory=dict)
    surface_losses: dict[str, int] = field(default_factory=dict)
    recent: deque = field(default_factory=lambda: deque(maxlen=10))
    opponents: list[tuple[str, str, bool]] = field(default_factory=list)
    last_date: Optional[str] = None
    rank: float = 999.0
    rank_points: float = 0.0

    def form(self):
        if not self.recent:
            return 0.5
        return sum(self.recent) / len(self.recent)

    def surface_form(self, surface):
        values = []
        for opponent, s, won in reversed(self.opponents):
            if s == surface:
                values.append(1.0 if won else 0.0)
                if len(values) >= 10:
                    break
        return sum(values) / len(values) if values else 0.5

    def matches(self):
        return self.wins + self.losses


class LeagueState:
    def __init__(self):
        self.players: dict[str, PlayerRecord] = {}
        self.elo = EloEngine()

        # (player, opponent) -> wins/losses from player's perspective
        self.h2h: dict[tuple[str, str], list[int]] = {}

    def player(self, name):
        if name not in self.players:
            self.players[name] = PlayerRecord(name=name)
        return self.players[name]

    def h2h_score(self, a, b):
        wins, losses = self.h2h.get((a, b), [0, 0])
        total = wins + losses
        if total == 0:
            return 0.0
        return (wins - losses) / total

    def common_opponents(self, a, b):
        a_opp = {x[0] for x in self.player(a).opponents}
        b_opp = {x[0] for x in self.player(b).opponents}
        return sorted(a_opp & b_opp)

    def _update_h2h(self, winner, loser):
        w = self.h2h.setdefault((winner, loser), [0, 0])
        w[0] += 1

        l = self.h2h.setdefault((loser, winner), [0, 0])
        l[1] += 1

    def record_result(
        self,
        winner,
        loser,
        surface,
        date,
        winner_rank=999.0,
        loser_rank=999.0,
        winner_rank_points=0.0,
        loser_rank_points=0.0,
    ):
        w = self.player(winner)
        l = self.player(loser)

        w.wins += 1
        l.losses += 1

        w.surface_wins[surface] = (
            w.surface_wins.get(surface, 0) + 1
        )
        l.surface_losses[surface] = (
            l.surface_losses.get(surface, 0) + 1
        )

        w.recent.append(1.0)
        l.recent.append(0.0)

        w.opponents.append((loser, surface, True))
        l.opponents.append((winner, surface, False))

        date_str = date.isoformat()
        w.last_date = date_str
        l.last_date = date_str

        w.rank = winner_rank
        l.rank = loser_rank
        w.rank_points = winner_rank_points
        l.rank_points = loser_rank_points

        self._update_h2h(winner, loser)
        self.elo.update(winner, loser, surface)

    def snapshot(self, a, b, surface):
        pa = self.player(a)
        pb = self.player(b)

        common = self.common_opponents(a, b)

        return {
            "elo_a": self.elo.rating(a),
            "elo_b": self.elo.rating(b),
            "surface_elo_a": self.elo.surface_rating(a, surface),
            "surface_elo_b": self.elo.surface_rating(b, surface),
            "elo_prob": self.elo.probability(a, b),
            "surface_elo_prob": self.elo.surface_probability(
                a, b, surface
            ),
            "rank_a": pa.rank,
            "rank_b": pb.rank,
            "rank_points_a": pa.rank_points,
            "rank_points_b": pb.rank_points,
            "form_a": pa.form(),
            "form_b": pb.form(),
            "surface_form_a": pa.surface_form(surface),
            "surface_form_b": pb.surface_form(surface),
            "matches_a": pa.matches(),
            "matches_b": pb.matches(),
            "h2h": self.h2h_score(a, b),
            "common_count": len(common),
        }

    def to_dict(self):
        return {
            "players": {
                name: {
                    "name": p.name,
                    "wins": p.wins,
                    "losses": p.losses,
                    "surface_wins": p.surface_wins,
                    "surface_losses": p.surface_losses,
                    "recent": list(p.recent),
                    "opponents": p.opponents,
                    "last_date": p.last_date,
                    "rank": p.rank,
                    "rank_points": p.rank_points,
                }
                for name, p in self.players.items()
            },
            "elo": {
                "base_rating": self.elo.base_rating,
                "k": self.elo.k,
                "ratings": self.elo.ratings,
                "surface_ratings": self.elo.surface_ratings,
                "counts": self.elo.counts,
                "surface_counts": self.elo.surface_counts,
            },
            "h2h": {
                f"{a}|||{b}": value
                for (a, b), value in self.h2h.items()
            },
        }

    @classmethod
    def from_dict(cls, data):
        state = cls()

        for name, raw in data["players"].items():
            p = PlayerRecord(name=name)
            p.wins = raw["wins"]
            p.losses = raw["losses"]
            p.surface_wins = raw["surface_wins"]
            p.surface_losses = raw["surface_losses"]
            p.recent = deque(
                raw["recent"],
                maxlen=10,
            )
            p.opponents = [
                tuple(x) for x in raw["opponents"]
            ]
            p.last_date = raw["last_date"]
            p.rank = raw["rank"]
            p.rank_points = raw["rank_points"]
            state.players[name] = p

        elo = data["elo"]
        state.elo.base_rating = elo["base_rating"]
        state.elo.k = elo["k"]
        state.elo.ratings = elo["ratings"]
        state.elo.surface_ratings = elo["surface_ratings"]
        state.elo.counts = elo["counts"]
        state.elo.surface_counts = elo["surface_counts"]

        state.h2h = {}
        for key, value in data["h2h"].items():
            a, b = key.split("|||")
            state.h2h[(a, b)] = value

        return state

    def save(self, path):
        path.write_text(
            json.dumps(
                self.to_dict(),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path):
        return cls.from_dict(
            json.loads(
                path.read_text(encoding="utf-8")
            )
        )
