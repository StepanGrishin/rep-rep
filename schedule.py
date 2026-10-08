import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta


URLS = [
    "https://www.tennisexplorer.com/next/",
    "https://noproxy.tennisexplorer.com/next/",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


BEST_OF_FIVE_KEYWORDS = (
    "australian open",
    "roland garros",
    "french open",
    "wimbledon",
    "us open",
)


class Match:
    def __init__(
        self,
        player_a,
        player_b,
        time="",
        tournament="",
        sets_a=None,
        sets_b=None,
        surface=None,
        date=None,
    ):
        self.player_a = player_a
        self.player_b = player_b
        self.time = time
        self.tournament = tournament
        self.sets_a = sets_a
        self.sets_b = sets_b
        self.surface = surface
        self.date = date

        self.finished = is_finished(
            tournament,
            sets_a,
            sets_b,
        )

    @property
    def winner(self):
        if not self.finished:
            return None

        if self.sets_a is None or self.sets_b is None:
            return None

        if self.sets_a > self.sets_b:
            return self.player_a

        if self.sets_b > self.sets_a:
            return self.player_b

        return None

    def __repr__(self):
        return (
            f"Match("
            f"{self.player_a} - {self.player_b}, "
            f"{self.time}, "
            f"{self.tournament}, "
            f"{self.date}"
            f")"
        )


def clean_text(text):
    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip()


def clean_player_name(name):
    """
    Sinner J. (1) -> Sinner J.
    Djokovic N. (6) -> Djokovic N.
    """

    name = clean_text(name)

    name = re.sub(
        r"\s*\(\d+\)\s*$",
        "",
        name,
    )

    return name.strip()


def clean_tournament_name(name):
    return clean_text(name)


def to_int(value):
    if value is None:
        return None

    value = clean_text(value)

    if not value:
        return None

    # 6^7 -> 6
    # 6^{7} -> 6
    value = re.sub(r"\^.*", "", value)
    value = re.sub(r"\{.*?\}", "", value)

    match = re.search(r"\d+", value)

    if not match:
        return None

    try:
        return int(match.group())
    except ValueError:
        return None


def is_finished(tournament, sets_a, sets_b):
    """
    Определяет, завершён ли матч.
    """

    if sets_a is None or sets_b is None:
        return False

    if sets_a == sets_b:
        return False

    tournament_lower = (
        tournament or ""
    ).lower()

    best_of_five = any(
        keyword in tournament_lower
        for keyword in BEST_OF_FIVE_KEYWORDS
    )

    if best_of_five:
        return sets_a >= 3 or sets_b >= 3

    return sets_a >= 2 or sets_b >= 2


def get_cell_text(row, selector):
    cell = row.select_one(selector)

    if cell is None:
        return ""

    return clean_text(
        cell.get_text(
            " ",
            strip=True,
        )
    )


def get_result_value(row):
    """
    Получает количество выигранных сетов
    из result.
    """

    result = row.select_one("td.result")

    if result is None:
        return None

    return to_int(
        result.get_text(
            " ",
            strip=True,
        )
    )


def find_tournament_from_row(row):
    """
    Пытается определить название турнира
    из строки заголовка.
    """

    # Основной вариант
    cell = row.select_one("td.t-name")

    if cell:
        link = cell.select_one("a")

        if link:
            name = clean_tournament_name(
                link.get_text(
                    " ",
                    strip=True,
                )
            )

            if name:
                return name

        name = clean_tournament_name(
            cell.get_text(
                " ",
                strip=True,
            )
        )

        if name:
            return name

    # Иногда название лежит в span
    span = row.select_one(
        "td.t-name span"
    )

    if span:
        name = clean_tournament_name(
            span.get_text(
                " ",
                strip=True,
            )
        )

        if name:
            return name

    return ""


def parse_table(table, target_date):
    """
    Парсит одну таблицу TennisExplorer.

    Типичная структура:

        tournament

        06:10 Player A
              Player B

        06:20 Player C
              Player D
    """

    matches = []

    current_tournament = ""

    rows = table.select("tr")

    i = 0

    while i < len(rows):

        row = rows[i]

        time_cell = row.select_one("td.time")

        # -------------------------------------------------
        # 1. Строка-заголовок турнира
        # -------------------------------------------------

        if time_cell is None:

            tournament = find_tournament_from_row(row)

            if tournament:

                # Не принимаем имена игроков за турнир
                if len(tournament) > 2:

                    current_tournament = (
                        tournament
                    )

            i += 1
            continue

        # -------------------------------------------------
        # 2. Нашли время матча
        # -------------------------------------------------

        time_text = clean_text(
            time_cell.get_text(
                " ",
                strip=True,
            )
        )

        player_cells = row.select(
            "td.t-name"
        )

        if not player_cells:

            i += 1
            continue

        player_a = clean_player_name(
            player_cells[0].get_text(
                " ",
                strip=True,
            )
        )

        if not player_a:

            i += 1
            continue

        # -------------------------------------------------
        # 3. Второй игрок
        # -------------------------------------------------

        player_b = ""

        if i + 1 < len(rows):

            next_row = rows[i + 1]

            next_player_cells = (
                next_row.select("td.t-name")
            )

            if next_player_cells:

                player_b = clean_player_name(
                    next_player_cells[0].get_text(
                        " ",
                        strip=True,
                    )
                )

        if not player_b:

            i += 1
            continue

        # -------------------------------------------------
        # 4. Счёт
        # -------------------------------------------------

        sets_a = get_result_value(row)

        sets_b = None

        if i + 1 < len(rows):

            sets_b = get_result_value(
                rows[i + 1]
            )

        # -------------------------------------------------
        # 5. Создаём матч
        # -------------------------------------------------

        match = Match(
            player_a=player_a,
            player_b=player_b,
            time=time_text,
            tournament=current_tournament,
            sets_a=sets_a,
            sets_b=sets_b,
            date=target_date,
        )

        matches.append(match)

        # Пропускаем строку второго игрока
        i += 2

    return matches


def parse_matches(html, target_date):
    """
    Главный HTML parser.
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    matches = []

    # -----------------------------------------------------
    # Сначала ищем таблицы result
    # -----------------------------------------------------

    tables = soup.select(
        "table.result"
    )

    # -----------------------------------------------------
    # Если таких таблиц нет — пробуем все таблицы
    # -----------------------------------------------------

    if not tables:

        tables = soup.find_all(
            "table"
        )

    for table in tables:

        try:

            table_matches = parse_table(
                table,
                target_date,
            )

            matches.extend(
                table_matches
            )

        except Exception as e:

            print(
                f"⚠️ Ошибка парсинга таблицы: {e}"
            )

    # -----------------------------------------------------
    # Удаляем дубликаты
    # -----------------------------------------------------

    unique = {}

    for match in matches:

        key = (
            match.date,
            match.time,
            match.player_a,
            match.player_b,
            match.tournament,
        )

        unique[key] = match

    return list(
        unique.values()
    )


def request_page(date, tour_type):
    """
    Загружает страницу TennisExplorer.

    tour_type:
        atp-single
        all
    """

    params = {
        "type": tour_type,
        "year": date.year,
        "month": date.month,
        "day": date.day,
    }

    last_error = None

    for url in URLS:

        try:

            response = requests.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=30,
            )

            response.raise_for_status()

            if len(response.text) < 1000:

                print(
                    f"⚠️ Слишком маленький ответ: "
                    f"{len(response.text)} bytes"
                )

                continue

            print(
                f"🌐 {response.status_code} "
                f"{response.url}"
            )

            print(
                f"📦 HTML: "
                f"{len(response.text)} bytes"
            )

            return response.text

        except Exception as e:

            last_error = e

            print(
                f"⚠️ Не удалось получить "
                f"{url}: {e}"
            )

    if last_error:

        print(
            f"❌ Все источники TennisExplorer "
            f"не сработали: {last_error}"
        )

    return ""


def get_matches_for_date(date):
    """
    Получает матчи ATP singles на конкретную дату.
    """

    target_date = date.strftime(
        "%d. %m. %Y"
    )

    print("")
    print("=" * 60)
    print(
        f"📅 Загружаем расписание: "
        f"{target_date}"
    )
    print("=" * 60)

    # -----------------------------------------------------
    # 1. Сначала ATP singles
    # -----------------------------------------------------

    html = request_page(
        date,
        "atp-single",
    )

    matches = []

    if html:

        matches = parse_matches(
            html,
            date,
        )

    print(
        f"🎾 ATP parser: "
        f"{len(matches)} матчей"
    )

    # -----------------------------------------------------
    # 2. Если ATP страница пустая,
    #    пробуем ALL
    # -----------------------------------------------------

    if not matches:

        print(
            "🔄 ATP расписание пустое. "
            "Пробуем общую страницу..."
        )

        html_all = request_page(
            date,
            "all",
        )

        if html_all:

            matches = parse_matches(
                html_all,
                date,
            )

            print(
                f"🎾 ALL parser: "
                f"{len(matches)} матчей"
            )

    # -----------------------------------------------------
    # 3. Выводим найденные матчи
    # -----------------------------------------------------

    if matches:

        print(
            f"✅ {target_date}: "
            f"найдено {len(matches)} матчей"
        )

        for match in matches[:10]:

            status = (
                "FINISHED"
                if match.finished
                else "UPCOMING"
            )

            print(
                f"   {match.time} | "
                f"{match.player_a} - "
                f"{match.player_b} | "
                f"{match.tournament} | "
                f"{status}"
            )

    else:

        print(
            f"❌ {target_date}: "
            f"матчи не найдены"
        )

    return matches


def get_today_matches():
    """
    Совместимость со старым bot.py.
    """

    today = datetime.now().date()

    return get_matches_for_date(
        today
    )


def get_upcoming_matches(days=2):
    """
    Возвращает:

        days=0:
            сегодня

        days=1:
            сегодня + завтра

        days=2:
            сегодня + завтра + послезавтра
    """

    today = datetime.now().date()

    all_matches = []

    print("")
    print(
        "🎾 Ищем расписание "
        f"с {today} "
        f"по {today + timedelta(days=days)}"
    )

    for offset in range(days + 1):

        date = (
            today
            + timedelta(days=offset)
        )

        try:

            matches = (
                get_matches_for_date(
                    date
                )
            )

            all_matches.extend(
                matches
            )

        except Exception as e:

            print(
                f"❌ Ошибка при обработке "
                f"{date}: {type(e).__name__}: {e}"
            )

    # -----------------------------------------------------
    # Удаляем дубликаты
    # -----------------------------------------------------

    unique = {}

    for match in all_matches:

        key = (
            match.date,
            match.time,
            match.player_a,
            match.player_b,
            match.tournament,
        )

        unique[key] = match

    result = list(
        unique.values()
    )

    # -----------------------------------------------------
    # Сортировка
    # -----------------------------------------------------

    def sort_key(match):

        return (
            match.date
            or datetime.max.date(),

            match.time
            or "99:99",

            match.tournament
            or "",

            match.player_a
            or "",
        )

    result.sort(
        key=sort_key
    )

    print("")
    print("=" * 60)
    print(
        f"🎾 ИТОГО найдено: "
        f"{len(result)} матчей"
    )
    print("=" * 60)

    return result
