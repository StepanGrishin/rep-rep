from datetime import date
from pathlib import Path

import joblib

from config import DATA_DIR, MODEL_DIR
from .data import load_matches, normalize_name
from .state import LeagueState
from .features import make_features, dataframe
from .common_opponents import common_opponent_details


class TennisPredictor:
    def __init__(
        self,
        model_path: Path | None = None,
        state_path: Path | None = None,
    ):
        self.model_path = model_path or (
            MODEL_DIR / "xgboost.pkl"
        )

        self.state_path = state_path or (
            MODEL_DIR / "state.json"
        )

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model not found: {self.model_path}. "
                f"Run `python training/train.py` first."
            )

        if not self.state_path.exists():
            raise FileNotFoundError(
                f"State not found: {self.state_path}. "
                f"Run `python training/train.py` first."
            )

        self.model = joblib.load(self.model_path)

        self._all_matches = None
        self._state_cache = {}
        self._alias_cache = None

    # =========================================================
    # Исторические матчи
    # =========================================================

    def _matches(self):
        if self._all_matches is None:
            self._all_matches = load_matches(DATA_DIR)

        return self._all_matches

    # =========================================================
    # Разрешение имени TennisExplorer -> имя из базы
    #
    # Например:
    #   Borges N. -> nuno borges
    #   Munar J.  -> jaume munar
    #   Tsitsipas S. -> stefanos tsitsipas
    # =========================================================

    # =========================================================
    # Разрешение имени TennisExplorer -> имя из базы
    #
    # Примеры:
    #   Borges N. -> nuno borges
    #   Munar J. -> jaume munar
    #   Tsitsipas S. -> stefanos tsitsipas
    # =========================================================

    def _build_aliases(self):
        if self._alias_cache is not None:
            return self._alias_cache

        aliases = {}

        players = set()

        for match in self._matches():
            players.add(match.winner)
            players.add(match.loser)

        for player in players:
            normalized = normalize_name(player)

            if not normalized:
                continue

            tokens = normalized.split()

            if len(tokens) < 2:
                continue

            # Исторические данные ATP:
            # "stefanos tsitsipas"
            #
            # Берём последнее слово как фамилию,
            # первое слово как имя.
            surname = tokens[-1]
            first_initial = tokens[0][0]

            alias = f"{surname} {first_initial}"

            aliases.setdefault(alias, set()).add(normalized)

        self._alias_cache = aliases

        print(
            f"DEBUG: построено alias: {len(aliases)}, "
            f"игроков: {len(players)}"
        )

        return aliases

    def _resolve_player(self, player):
        normalized = normalize_name(player)

        if not normalized:
            return normalized

    # Все игроки из исторических данных
        players = set()

        for match in self._matches():
            players.add(normalize_name(match.winner))
            players.add(normalize_name(match.loser))

    # 1. Точное совпадение
        if normalized in players:
            return normalized

        tokens = normalized.split()

    # Для TennisExplorer формат обычно:
    # "Tirante T."
    # "Jodar R."
        if len(tokens) >= 2:
            surname = tokens[0]
            initial = tokens[1][0]

            candidates = []

            for candidate in players:
                candidate_tokens = candidate.split()

                if len(candidate_tokens) < 2:
                    continue

                candidate_surname = candidate_tokens[-1]
                candidate_initial = candidate_tokens[0][0]

                if (
                    candidate_surname == surname
                and candidate_initial == initial
                ):
                    candidates.append(candidate)

            if len(candidates) == 1:
                print(
                f"DEBUG RESOLVE OK: "
                f"{player} -> {candidates[0]}"
            )
                return candidates[0]

            if len(candidates) > 1:
                print(
                f"DEBUG RESOLVE AMBIGUOUS: "
                f"{player} -> {candidates}"
            )

    # 2. Попытка найти только по фамилии
        if len(tokens) >= 1:
            surname = tokens[0]

            surname_candidates = []

            for candidate in players:
                candidate_tokens = candidate.split()

                if not candidate_tokens:
                    continue

                if candidate_tokens[-1] == surname:
                    surname_candidates.append(candidate)

            if len(surname_candidates) == 1:
                print(
                f"DEBUG RESOLVE SURNAME: "
                f"{player} -> {surname_candidates[0]}"
            )
                return surname_candidates[0]
    
        print(
        f"DEBUG RESOLVE FAIL: "
        f"{player} -> {normalized}"
    )

        return normalized

    # =========================================================
    # Построение состояния до даты матча
    # =========================================================

    def _build_state(self, before_date=None):
        key = str(before_date) if before_date else "all"

        if key in self._state_cache:
            return self._state_cache[key]

        state = LeagueState()

        for match in self._matches():

            if before_date is not None:
                if match.date.date() >= before_date:
                    break

            state.record_result(
                winner=match.winner,
                loser=match.loser,
                surface=match.surface,
                date=match.date,
                winner_rank=match.winner_rank,
                loser_rank=match.loser_rank,
                winner_rank_points=match.winner_rank_points,
                loser_rank_points=match.loser_rank_points,
            )

        self._state_cache[key] = state

        return state

    # =========================================================
    # SCORE твоего оригинального алгоритма
    #
    # Для каждого общего соперника:
    #
    #   winrate A > winrate B -> A +1
    #   winrate B > winrate A -> B +1
    #   равенство -> никто не получает балл
    #
    # Это логика из sportbot.
    # =========================================================

    def _common_opponent_score(
        self,
        state,
        player_a,
        player_b,
        details,
    ):
        score_a = 0
        score_b = 0

        scored_opponents = []

        for item in details:
            a_wins = item["a_wins"]
            a_losses = item["a_losses"]

            b_wins = item["b_wins"]
            b_losses = item["b_losses"]

            a_matches = a_wins + a_losses
            b_matches = b_wins + b_losses

            if a_matches == 0 or b_matches == 0:
                continue

            a_winrate = a_wins / a_matches
            b_winrate = b_wins / b_matches

            if a_winrate > b_winrate:
                score_a += 1
                winner = "a"

            elif b_winrate > a_winrate:
                score_b += 1
                winner = "b"

            else:
                winner = "draw"

            scored_opponents.append(
                {
                    "opponent": item["opponent"],
                    "a_wins": a_wins,
                    "a_losses": a_losses,
                    "b_wins": b_wins,
                    "b_losses": b_losses,
                    "a_winrate": a_winrate,
                    "b_winrate": b_winrate,
                    "score_winner": winner,
                }
            )

        total = score_a + score_b

        if total == 0:
            score_probability_a = 50.0
            score_probability_b = 50.0
        else:
            score_probability_a = (
                score_a / total * 100.0
            )
            score_probability_b = (
                score_b / total * 100.0
            )

        if score_a > score_b:
            score_winner = player_a
        elif score_b > score_a:
            score_winner = player_b
        else:
            score_winner = None

        return {
            "score_a": score_a,
            "score_b": score_b,
            "score_probability_a": score_probability_a,
            "score_probability_b": score_probability_b,
            "score_winner": score_winner,
            "score_details": scored_opponents,
        }

    # =========================================================
    # Основной prediction
    # =========================================================

    def predict(
        self,
        player_a,
        player_b,
        surface="Hard",
        before_date=None,
    ):
        if before_date is None:
            before_date = date.today()

        # -----------------------------------------------------
        # Оригинальные имена сохраняем для Telegram
        # -----------------------------------------------------

        original_player_a = player_a
        original_player_b = player_b

        # -----------------------------------------------------
        # Разрешаем имена TennisExplorer
        # -----------------------------------------------------

        a = self._resolve_player(player_a)
        b = self._resolve_player(player_b)
        print(
            f"DEBUG RESOLVE: "
            f"{player_a} -> {a} | "
            f"{player_b} -> {b}"
        )

        # -----------------------------------------------------
        # Строим историческое состояние
        # -----------------------------------------------------

        state = self._build_state(before_date)

        # -----------------------------------------------------
        # ML snapshot
        # -----------------------------------------------------

        snapshot = state.snapshot(
            a,
            b,
            surface,
        )

        row = make_features(snapshot)

        x = dataframe([row])

        probability_a = float(
            self.model.predict_proba(x)[0][1]
        )

        probability_b = 1.0 - probability_a

        winner = (
            original_player_a
            if probability_a >= probability_b
            else original_player_b
        )

        # -----------------------------------------------------
        # Общие соперники
        # -----------------------------------------------------

        details = common_opponent_details(
            state,
            a,
            b,
        )

        # -----------------------------------------------------
        # SCORE оригинального sportbot
        # -----------------------------------------------------

        common_score = self._common_opponent_score(
            state=state,
            player_a=original_player_a,
            player_b=original_player_b,
            details=details,
        )

        # -----------------------------------------------------
        # Возвращаем всё необходимое
        # -----------------------------------------------------

        return {
            # Имена для отображения
            "player_a": original_player_a,
            "player_b": original_player_b,

            # Канонические имена из базы
            "resolved_player_a": a,
            "resolved_player_b": b,

            # ML probability
            "probability_a": probability_a * 100.0,
            "probability_b": probability_b * 100.0,

            # ML winner
            "winner": winner,

            # ELO
            "elo_a": snapshot["elo_a"],
            "elo_b": snapshot["elo_b"],

            # Surface ELO
            "surface_elo_a": snapshot[
                "surface_elo_a"
            ],
            "surface_elo_b": snapshot[
                "surface_elo_b"
            ],

            # Дополнительные вероятности ELO
            "elo_prob": snapshot["elo_prob"],
            "surface_elo_prob": snapshot[
                "surface_elo_prob"
            ],

            # H2H
            "h2h": snapshot["h2h"],

            # Общие соперники
            "common_count": snapshot[
                "common_count"
            ],

            # Подробности общих соперников
            "details": details,

            # -------------------------------------------------
            # Твой оригинальный алгоритм
            # -------------------------------------------------

            "score_a": common_score[
                "score_a"
            ],
            "score_b": common_score[
                "score_b"
            ],

            "score_probability_a": common_score[
                "score_probability_a"
            ],
            "score_probability_b": common_score[
                "score_probability_b"
            ],

            "score_winner": common_score[
                "score_winner"
            ],

            "score_details": common_score[
                "score_details"
            ],

            # ML features
            "features": row,
        }
