"""
core/predictions_log.py
------------------------
Log ramalan (base) yang PERNAH digunakan secara forward-looking — bukan
backtest retrospektif yang jana semula base ke belakang. Bila keputusan
sebenar bagi tarikh yang dilog itu sudah keluar, boleh disemak & dikira
kadar padanan SEBENAR (rekod jujur, bukan simulasi).

Nota penting: fail log ni (`data/predictions_log.json`) tertakluk sama
macam `data/draws.txt` — kalau environment Streamlit reset (cth:
redeploy container), data log ni turut hilang melainkan disimpan/commit
semula secara manual. Sama batasan macam draws.txt.
"""

import json
from pathlib import Path

from core.formula_break import check_against_base

LOG_FILE = Path(__file__).parent.parent / "data" / "predictions_log.json"


def load_predictions() -> list[dict]:
    """Muatkan semua ramalan yang pernah dilog. Pulang senarai kosong kalau tiada."""
    if not LOG_FILE.exists():
        return []
    try:
        return json.loads(LOG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_predictions(records: list[dict]) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def log_prediction(
    date_str: str,
    base: list[list[str]],
    recent_n: int,
    rank_range: tuple[int, int],
    mode: str,
    known_dates: set[str] | None = None,
) -> tuple[bool, str]:
    """
    Simpan satu ramalan (base) bagi `date_str`. Kalau dah ada log utk
    tarikh + mod yang sama, GANTI (elak pendua kalau base dijana semula
    utk tarikh sama). Kalau `known_dates` diberi dan `date_str` SUDAH
    ada keputusan sebenar di dalamnya, TOLAK log ini (elak "ramalan"
    palsu selepas-fakta) dan pulangkan mesej sebab.
    """
    if known_dates is not None and date_str in known_dates:
        return False, (
            f"{date_str} sudah ada keputusan sebenar direkodkan — tak boleh log sbg "
            "ramalan forward-looking selepas-fakta."
        )

    records = load_predictions()
    records = [r for r in records if not (r["date"] == date_str and r["mode"] == mode)]
    records.append({
        "date": date_str,
        "base": base,
        "recent_n": recent_n,
        "rank_range": list(rank_range),
        "mode": mode,
    })
    records.sort(key=lambda r: r["date"])
    _save_predictions(records)
    return True, f"Ramalan bagi {date_str} ({mode}) berjaya disimpan."


def reconcile_predictions(draws: list[dict]) -> list[dict]:
    """
    Padankan setiap ramalan yang dilog dgn keputusan SEBENAR (kalau dah
    keluar dalam `draws`). Pulangkan status tiap satu: Menunggu keputusan
    / Match Penuh / X dari 4 padanan.
    """
    draw_by_date = {d["date"]: d["number"] for d in draws}
    records = load_predictions()
    out = []
    for r in records:
        actual = draw_by_date.get(r["date"])
        if actual is None:
            status = "⏳ Menunggu keputusan"
            actual_display = "—"
        else:
            flags = check_against_base(actual, r["base"])
            match_count = sum(flags)
            status = "🎯 Match Penuh" if match_count == 4 else f"{match_count}/4 Padanan"
            actual_display = actual
        out.append({
            "Tarikh": r["date"],
            "Mod": r["mode"],
            "Base Digunakan": " / ".join("".join(p) for p in r["base"]),
            "Keputusan Sebenar": actual_display,
            "Status": status,
        })
    return out


def prediction_summary(reconciled: list[dict]) -> dict:
    """Ringkasan ringkas: berapa selesai, berapa match penuh, kadar %."""
    decided = [r for r in reconciled if r["Status"] != "⏳ Menunggu keputusan"]
    full = [r for r in decided if r["Status"] == "🎯 Match Penuh"]
    rate = round(len(full) / len(decided) * 100, 2) if decided else 0.0
    return {
        "total": len(reconciled),
        "decided": len(decided),
        "pending": len(reconciled) - len(decided),
        "full_match": len(full),
        "rate": rate,
    }
