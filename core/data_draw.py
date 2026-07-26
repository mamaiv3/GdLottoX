"""
core/data_draw.py
------------------
Pengurusan data draw 4D (GD Lotto): baca, tambah secara manual, dan
kemas kini keputusan terkini secara automatik.

Ini SATU-SATUNYA sumber data mentah yang digunakan oleh Formula Break
dan Wheelpick — dikekalkan berasingan supaya senang diselenggara.
"""

import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DRAW_FILE = "data/draws.txt"


def get_draw_countdown_from_last_8pm() -> timedelta:
    """Anggaran baki masa sebelum keputusan draw seterusnya (asas 8:00 PM, waktu Malaysia)."""
    now = datetime.now(ZoneInfo("Asia/Kuala_Lumpur"))
    today_8pm = now.replace(hour=20, minute=0, second=0, microsecond=0)
    last_8pm = today_8pm - timedelta(days=1) if now < today_8pm else today_8pm
    return (last_8pm + timedelta(days=1)) - now


def load_draws(file_path: str = DRAW_FILE) -> list[dict]:
    """Baca semua draw dari fail teks (format: 'YYYY-MM-DD NNNN' per baris)."""
    if not os.path.exists(file_path):
        return []
    draws = []
    with open(file_path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) == 2 and re.match(r"^\d{4}$", parts[1]):
                draws.append({"date": parts[0], "number": parts[1]})
    return sorted(draws, key=lambda d: d["date"])


def add_draw(date_str: str, number: str, file_path: str = DRAW_FILE) -> tuple[bool, str]:
    """Tambah satu draw secara manual. Menolak tarikh/nombor tak sah atau pendua."""
    date_str = date_str.strip()
    number = number.strip()

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return False, "❌ Format tarikh mesti YYYY-MM-DD."
    if not re.match(r"^\d{4}$", number):
        return False, "❌ Nombor mesti tepat 4 digit (0000–9999)."

    draws = load_draws(file_path)
    if any(d["date"] == date_str for d in draws):
        return False, f"⚠️ Draw untuk {date_str} sudah wujud."

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "a") as f:
        f.write(f"{date_str} {number}\n")
    return True, "✅ Draw berjaya ditambah."


def scrape_latest(file_path: str = DRAW_FILE, max_days_back: int = 181) -> str:
    """
    Cuba tarik keputusan terkini dari gdlotto.net secara automatik.
    Perlukan sambungan internet semasa aplikasi ini dijalankan (streamlit run).
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return "⚠️ Modul 'requests' / 'beautifulsoup4' tiada. Sila tambah draw secara manual."

    def get_1st_prize(date_str: str):
        url = f"https://gdlotto.net/results/ajax/_result.aspx?past=1&d={date_str}"
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            tag = soup.find("span", id="1stPz")
            txt = tag.text.strip() if tag else ""
            return txt if txt.isdigit() and len(txt) == 4 else None
        except Exception:
            return None

    draws = load_draws(file_path)
    existing = {d["date"] for d in draws}

    tz = ZoneInfo("Asia/Kuala_Lumpur")
    now_my = datetime.now(tz)
    cutoff_hour = 20
    latest_date = now_my.date() if now_my.hour >= cutoff_hour else (now_my - timedelta(days=1)).date()

    last_date = (
        datetime.strptime(draws[-1]["date"], "%Y-%m-%d").date()
        if draws else (now_my - timedelta(days=max_days_back)).date()
    )

    current = last_date + timedelta(days=1)
    added = []
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "a") as f:
        while current <= latest_date:
            ds = current.strftime("%Y-%m-%d")
            current += timedelta(days=1)
            if ds in existing:
                continue
            prize = get_1st_prize(ds)
            if prize:
                f.write(f"{ds} {prize}\n")
                added.append(ds)

    if added:
        return f"✔️ {len(added)} draw baru ditambah ({added[0]} → {added[-1]})."
    return "ℹ️ Tiada draw baru ditemui buat masa ini."
