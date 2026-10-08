from pathlib import Path
import requests
from config import DATA_DIR, START_YEAR, END_YEAR

BASE_URL = (
    "https://raw.githubusercontent.com/"
    "Aneeshers/tennis-sackmann-archive/main/atp/"
)

DATA_DIR.mkdir(parents=True, exist_ok=True)

for year in range(START_YEAR, END_YEAR + 1):
    filename = f"atp_matches_{year}.csv"
    path = DATA_DIR / filename

    if path.exists():
        print(f"[SKIP] {filename}")
        continue

    url = BASE_URL + filename
    print(f"[DOWNLOAD] {year}")

    response = requests.get(url, timeout=60)
    if response.status_code == 200:
        path.write_bytes(response.content)
        print(f"[OK] {path}")
    else:
        print(f"[ERROR] {year}: HTTP {response.status_code}")
