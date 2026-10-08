from dataclasses import dataclass, field
import math


def _expected(rating_a, rating_b):
    return 1.0 / (
        1.0 + 10.0 ** ((rating_b - rating_a) / 400.0)
    )


@dataclass
class EloEngine:
    base_rating: float = 1500.0
    k: float | None = None
    ratings: dict[str, float] = field(default_factory=dict)
    surface_ratings: dict[str, dict[str, float]] = field(
        default_factory=dict
    )
    counts: dict[str, int] = field(default_factory=dict)
    surface_counts: dict[str, dict[str, int]] = field(
        default_factory=dict
    )

    def rating(self, player):
        return self.ratings.get(player, self.base_rating)

    def surface_rating(self, player, surface):
        return self.surface_ratings.get(
            surface, {}
        ).get(player, self.base_rating)

    def _k(self, player):
        if self.k is not None:
            return self.k

        matches = self.counts.get(player, 0)
        return 250.0 / ((matches + 5.0) ** 0.4)

    def _surface_k(self, player, surface):
        if self.k is not None:
            return self.k

        matches = self.surface_counts.get(
            surface, {}
        ).get(player, 0)
        return 250.0 / ((matches + 5.0) ** 0.4)

    def probability(self, player_a, player_b):
        return _expected(
            self.rating(player_a),
            self.rating(player_b),
        )

    def surface_probability(self, player_a, player_b, surface):
        return _expected(
            self.surface_rating(player_a, surface),
            self.surface_rating(player_b, surface),
        )

    def update(self, winner, loser, surface):
        winner_rating = self.rating(winner)
        loser_rating = self.rating(loser)

        expected_w = _expected(
            winner_rating,
            loser_rating,
        )
        k_w = self._k(winner)
        k_l = self._k(loser)

        self.ratings[winner] = (
            winner_rating + k_w * (1.0 - expected_w)
        )
        self.ratings[loser] = (
            loser_rating + k_l * (0.0 - (1.0 - expected_w))
        )

        self.counts[winner] = self.counts.get(winner, 0) + 1
        self.counts[loser] = self.counts.get(loser, 0) + 1

        sr = self.surface_ratings.setdefault(surface, {})
        sc = self.surface_counts.setdefault(surface, {})

        winner_sr = sr.get(winner, self.base_rating)
        loser_sr = sr.get(loser, self.base_rating)

        expected_sw = _expected(winner_sr, loser_sr)
        sk_w = self._surface_k(winner, surface)
        sk_l = self._surface_k(loser, surface)

        sr[winner] = winner_sr + sk_w * (1.0 - expected_sw)
        sr[loser] = loser_sr + sk_l * (0.0 - (1.0 - expected_sw))

        sc[winner] = sc.get(winner, 0) + 1
        sc[loser] = sc.get(loser, 0) + 1
