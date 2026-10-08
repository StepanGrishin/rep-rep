import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import BOT_TOKEN, MIN_COMMON_OPPONENTS
from predictor import TennisPredictor
from schedule import get_upcoming_matches
from predictor.data import normalize_name


logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

predictor = TennisPredictor()

today_matches = {}


def infer_surface(tournament):
    name = (tournament or "").lower()

    if any(
        x in name
        for x in (
            "french open",
            "roland garros",
            "monte carlo",
            "rome",
            "madrid",
            "barcelona",
            "hamburg",
        )
    ):
        return "Clay"

    if "wimbledon" in name:
        return "Grass"

    return "Hard"


# ============================================================
# СОПОСТАВЛЕНИЕ ИМЁН
# ============================================================

def build_player_aliases():
    """
    Создаёт словарь:

        'borges n.' -> 'nuno borges'
        'munar j.'  -> 'jaume munar'
        'tsitsipas s.' -> 'stefanos tsitsipas'

    Источник имён — исторический ATP CSV.
    """

    aliases = {}

    try:
        historical_matches = predictor._matches()
    except Exception:
        logging.exception(
            "Не удалось загрузить исторические матчи"
        )
        return aliases

    for match in historical_matches:

        for player in (
            match.winner,
            match.loser,
        ):

            if not player:
                continue

            canonical = normalize_name(player)

            parts = canonical.split()

            if len(parts) < 2:
                continue

            surname = parts[-1]
            first_name = parts[0]

            # Основной ключ:
            # surname + первая буква имени
            key = f"{surname} {first_name[0]}"

            aliases.setdefault(
                key,
                set(),
            ).add(canonical)

    # Оставляем только однозначные соответствия
    result = {}

    for key, values in aliases.items():

        if len(values) == 1:
            result[key] = next(iter(values))

    print(
        f"👤 Загружено алиасов игроков: "
        f"{len(result)}"
    )

    return result


PLAYER_ALIASES = build_player_aliases()


def resolve_player_name(name):
    """
    Преобразует имя TennisExplorer:

        Borges N.
        Munar J.
        Tsitsipas S.

    в имя из исторического dataset.

    Если сопоставить не удалось —
    возвращает исходное имя.
    """

    if not name:
        return name

    normalized = normalize_name(name)

    parts = normalized.split()

    if len(parts) < 2:
        return name

    # TennisExplorer обычно:
    #
    # Borges N.
    # Munar J.
    #
    # После normalize:
    #
    # borges n.
    # munar j.

    surname = parts[0]
    initial = parts[1][0]

    key = f"{surname} {initial}"

    resolved = PLAYER_ALIASES.get(key)

    if resolved:
        print(
            f"🔗 {name} -> {resolved}"
        )
        return resolved

    return name


# ============================================================
# АНАЛИЗ
# ============================================================

def analyze_today():
    LOOKAHEAD_DAYS = 2
    today = datetime.now().date()

    matches = get_upcoming_matches(
        days=LOOKAHEAD_DAYS
    )

    print("========================================")
    print(
        f"DEBUG: schedule returned "
        f"{len(matches)} matches"
    )

    for m in matches[:20]:
        print(
            f"DEBUG MATCH: "
            f"{m.date} | "
            f"{m.time} | "
            f"{m.player_a} - {m.player_b} | "
            f"{m.tournament}"
        )

    print("========================================")
    print(
        f"🎾 Получено матчей из schedule: "
        f"{len(matches)}"
    )

    upcoming = []

    # Общая статистика
    wins = 0
    losses = 0
    skipped = 0

    # Статистика по дням
    daily_stats = {}

    for match in matches:

        surface = getattr(
            match,
            "surface",
            None,
        ) or infer_surface(match.tournament)

        result = predictor.predict(
            match.player_a,
            match.player_b,
            surface=surface,
            before_date=today,
        )
        print(
    "DEBUG PREDICT:",
    match.player_a,
    "vs",
    match.player_b,
    "| resolved:",
    result.get("resolved_player_a"),
    "vs",
    result.get("resolved_player_b"),
    "| common:",
    result.get("common_count"),
    "| score:",
    result.get("score_a"),
    "-",
    result.get("score_b"),
        )

        # --------------------------------------------------
        # Фильтр: нужен хотя бы один общий соперник
        # --------------------------------------------------

        has_prediction = (
            result["common_count"]
            >= MIN_COMMON_OPPONENTS
        )

        # --------------------------------------------------
        # Определяем дату матча
        # --------------------------------------------------

        match_date = match.date

        if hasattr(match_date, "date"):
            match_day = match_date.date()
        else:
            match_day = match_date

        day_key = str(match_day)

        if day_key not in daily_stats:
            daily_stats[day_key] = {
                "total": 0,
                "wins": 0,
                "losses": 0,
                "skipped": 0,
            }

        # --------------------------------------------------
        # Завершённый матч
        # --------------------------------------------------

        if match.finished:

            if (
                has_prediction
                and result["winner"]
                and match.winner
            ):
                daily_stats[day_key]["total"] += 1

                if result["winner"] == match.winner:
                    wins += 1
                    daily_stats[day_key]["wins"] += 1
                else:
                    losses += 1
                    daily_stats[day_key]["losses"] += 1

            else:
                skipped += 1
                daily_stats[day_key]["skipped"] += 1

        # --------------------------------------------------
        # Предстоящий матч
        # --------------------------------------------------

        elif (
            has_prediction
            and result["common_count"] > 0
        ):
            upcoming.append(
                (match, result)
            )

    return upcoming, {
        "total": len(matches),
        "wins": wins,
        "losses": losses,
        "skipped": skipped,
        "daily": daily_stats,
    }


# ============================================================
# TELEGRAM
# ============================================================

@dp.message(CommandStart())
async def start_handler(message: Message):
    await show_today_matches(message)


async def show_today_matches(message: Message):

    global today_matches

    try:

        upcoming, stats = await asyncio.to_thread(
            analyze_today
        )

    except Exception:

        logging.exception(
            "Ошибка анализа расписания"
        )

        await message.answer(
            "❌ Не удалось получить расписание "
            "или построить прогноз."
        )

        return

    if stats["total"] == 0:

        await message.answer(
            "Сегодня матчей не найдено."
        )

        return

    today_matches = {
        str(i): pair
        for i, pair in enumerate(
            upcoming
        )
    }

    keyboard = []

    for i, (match, _) in today_matches.items():

        keyboard.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"🎾 {match.player_a} — "
                        f"{match.player_b}"
                    ),
                    callback_data=f"match:{i}",
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data="refresh",
            )
        ]
    )

    text = (
        "🎾 <b>Предстоящие матчи "
        "на ближайшие 2 дня</b>\n\n"
    )

    if upcoming:

        text += (
            "Выбери матч для анализа."
        )

    else:

        text += (
            "Предстоящих матчей с доступным "
            "прогнозом нет."
        )

    text += "\n\n" + format_stats(
        stats
    )

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard
        ),
        parse_mode="HTML",
    )


def format_stats(stats):
    wins = stats["wins"]
    losses = stats["losses"]
    skipped = stats["skipped"]

    done = wins + losses

    text = "📊 <b>Статистика ML-прогнозов</b>\n\n"

    # --------------------------------------------------
    # Общая статистика
    # --------------------------------------------------

    if done == 0:
        text += (
            "Пока нет завершённых матчей "
            "с прогнозом.\n"
        )
    else:
        accuracy = wins / done * 100

        text += (
            f"🎯 Всего прогнозов: <b>{done}</b>\n"
            f"✅ Угадали: <b>{wins}</b>\n"
            f"❌ Не угадали: <b>{losses}</b>\n"
            f"📈 Точность: <b>{accuracy:.1f}%</b>\n"
        )

    if skipped:
        text += (
            f"⏭ Без прогноза: <b>{skipped}</b>\n"
        )

    # --------------------------------------------------
    # Статистика по дням
    # --------------------------------------------------

    daily = stats.get("daily", {})

    if daily:
        text += "\n📅 <b>По дням:</b>\n"

        for day, data in sorted(
            daily.items()
        ):
            day_wins = data["wins"]
            day_losses = data["losses"]
            day_skipped = data["skipped"]

            day_done = (
                day_wins + day_losses
            )

            if day_done > 0:
                day_accuracy = (
                    day_wins / day_done * 100
                )

                text += (
                    f"\n<b>{day}</b>\n"
                    f"✅ {day_wins}  "
                    f"❌ {day_losses}  "
                    f"📈 {day_accuracy:.0f}%"
                )

            else:
                text += (
                    f"\n<b>{day}</b>\n"
                    "Нет завершённых прогнозов"
                )

            if day_skipped:
                text += (
                    f"\n⏭ Без прогноза: "
                    f"{day_skipped}"
                )

    return text


# ============================================================
# CALLBACK: REFRESH
# ============================================================

@dp.callback_query(
    F.data == "refresh"
)
async def refresh_handler(
    callback: CallbackQuery
):

    await callback.answer(
        "Обновляю..."
    )

    await show_today_matches(
        callback.message
    )


# ============================================================
# CALLBACK: MATCH
# ============================================================

@dp.callback_query(
    F.data.startswith("match:")
)
async def match_handler(
    callback: CallbackQuery
):

    await callback.answer()

    index = callback.data.split(":")[1]

    pair = today_matches.get(
        index
    )

    if not pair:

        await callback.message.answer(
            "❌ Матч устарел. "
            "Нажми /start"
        )

        return

    match, result = pair

    await callback.message.answer(
        format_prediction(
            match,
            result,
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="refresh",
                    )
                ]
            ]
        ),
        parse_mode="HTML",
    )


# ============================================================
# FORMAT PREDICTION
# ============================================================

def format_prediction(match, result):
    a = result["player_a"]
    b = result["player_b"]

    pa = result["probability_a"]
    pb = result["probability_b"]

    winner = result["winner"]

    surface = (
        getattr(match, "surface", None)
        or infer_surface(match.tournament)
    )

    # ELO
    elo_a = result["elo_a"]
    elo_b = result["elo_b"]

    # Surface ELO
    surface_elo_a = result["surface_elo_a"]
    surface_elo_b = result["surface_elo_b"]

    # Твой алгоритм общих соперников
    score_a = result.get("score_a", 0)
    score_b = result.get("score_b", 0)

    score_probability_a = result.get(
        "score_probability_a",
        50.0,
    )
    score_probability_b = result.get(
        "score_probability_b",
        50.0,
    )

    score_winner = result.get(
        "score_winner"
    )

    common_count = result.get(
        "common_count",
        0,
    )

    h2h = result.get(
        "h2h",
        0.0,
    )

    text = (
        f"🎾 <b>{a} — {b}</b>\n\n"
        f"🏆 {match.tournament or 'ATP'}\n"
        f"🎾 Покрытие: <b>{surface}</b>\n"
    )

    if match.time:
        text += f"🕐 {match.time}\n"

    text += (
        "\n🤖 <b>ML prediction</b>\n\n"
        f"🟢 {a}: <b>{pa:.1f}%</b>\n"
        f"🔵 {b}: <b>{pb:.1f}%</b>\n\n"

        "📊 <b>ELO</b>\n"
        f"🟢 {a}: <b>{elo_a:.0f}</b>\n"
        f"🔵 {b}: <b>{elo_b:.0f}</b>\n\n"

        f"🔥 <b>Surface ELO — {surface}</b>\n"
        f"🟢 {a}: <b>{surface_elo_a:.0f}</b>\n"
        f"🔵 {b}: <b>{surface_elo_b:.0f}</b>\n\n"

        f"🤝 <b>Общих соперников:</b> "
        f"{common_count}\n"

        f"⚔️ <b>H2H score:</b> "
        f"{h2h:+.2f}\n\n"

        "🧠 <b>Твой алгоритм</b>\n"
        f"🟢 {a}: <b>{score_a}</b>\n"
        f"🔵 {b}: <b>{score_b}</b>\n"
        f"📈 Счёт: <b>{score_a} — {score_b}</b>\n"
        f"📊 Условная вероятность: "
        f"<b>{score_probability_a:.0f}% — "
        f"{score_probability_b:.0f}%</b>\n"
    )

    if score_winner:
        text += (
            f"🏅 Алгоритм склоняется к: "
            f"<b>{score_winner}</b>\n"
        )
    else:
        text += (
            "🏅 Алгоритм: <b>равный счёт</b>\n"
        )

    text += (
        f"\n🏆 <b>ML прогноз: {winner}</b>"
    )

    details = result.get("details") or []

    if details:
        text += "\n\n<b>Общие соперники:</b>"

        for item in details[:10]:
            opponent = item["opponent"]

            a_wins = item["a_wins"]
            a_losses = item["a_losses"]

            b_wins = item["b_wins"]
            b_losses = item["b_losses"]

            text += (
                f"\n\n<b>{opponent}</b>\n"
                f"🟢 {a}: {a_wins}-{a_losses}\n"
                f"🔵 {b}: {b_wins}-{b_losses}"
            )

    return text


# ============================================================
# MAIN
# ============================================================

async def main():

    print(
        "Tennis ML predictor bot started..."
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":
    asyncio.run(main())
