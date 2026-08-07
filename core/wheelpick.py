"""
core/wheelpick.py
-------------------
Wheelpick Generator: hasilkan & tapis kombinasi 4D daripada mana-mana
base 4-posisi (biasanya hasil Formula Break) mengikut pelbagai kriteria.
"""

import itertools
from collections import Counter

from core.formula_break import check_against_base, generate_break_base


def get_like_dislike_digits(draws: list[dict], recent_n: int = 30) -> tuple[list[str], list[str]]:
    """
    Dari draw terkini, kenal pasti top-3 digit paling kerap ('like')
    dan bottom-3 paling jarang ('dislike') — untuk bantu tapisan Wheelpick.
    """
    recent = [d["number"] for d in draws[-recent_n:] if len(d.get("number", "")) == 4]
    cnt = Counter()
    for num in recent:
        cnt.update(num)
    most = [d for d, _ in cnt.most_common(3)]
    least = [d for d, _ in cnt.most_common()[-3:]] if len(cnt) >= 3 else []
    return most, least


def generate_wheel_combos(base: list[list[str]], lot: str = "0.10", arah: str = "kiri") -> list[str]:
    """
    Hasilkan semua kombinasi dari base (list of 4 lists), format "NNNN#####lot".
    arah: 'kiri' (P1→P4) atau 'kanan' (P4→P1).
    """
    if arah == "kanan":
        base = list(reversed(base))
    elif arah != "kiri":
        raise ValueError("arah mesti 'kiri' atau 'kanan'")

    combos = []
    for digits in itertools.product(*base):
        num = "".join(digits)
        combos.append(f"{num}#####{lot}")
    return combos


def filter_wheel_combos(
    combos: list[str],
    draws: list[dict],
    no_repeat: bool = False,
    no_triple: bool = False,
    no_pair: bool = False,
    no_ascend: bool = False,
    use_history: bool = False,
    sim_limit: int = 4,
    likes: list[str] | None = None,
    dislikes: list[str] | None = None,
) -> list[str]:
    """Tapis senarai kombinasi ("NNNN#####lot") mengikut kriteria yang dipilih."""
    past = {d["number"] for d in draws}
    last = draws[-1]["number"] if draws else "0000"
    likes = likes or []
    dislikes = dislikes or []
    out = []

    for entry in combos:
        num, _ = entry.split("#####")
        digs = list(num)

        if no_repeat and len(set(digs)) < 4:
            continue
        if no_triple and any(digs.count(d) >= 3 for d in set(digs)):
            continue
        if no_pair and any(digs.count(d) == 2 for d in set(digs)):
            continue
        if no_ascend and num in ["0123", "1234", "2345", "3456", "4567", "5678", "6789"]:
            continue
        if use_history and num in past:
            continue
        sim = sum(1 for a, b in zip(num, last) if a == b)
        if sim > sim_limit:
            continue
        if likes and not any(d in likes for d in digs):
            continue
        if dislikes and any(d in dislikes for d in digs):
            continue

        out.append(entry)
    return out


def rank_combos(
    combos: list[str],
    draws: list[dict],
    recent_n: int = 50,
    top_n: int = 10,
) -> list[dict]:
    """
    Skor & susun kombinasi ("NNNN#####lot") ikut kekerapan SEBENAR setiap
    digit pada setiap posisi (P1–P4) dalam `recent_n` draw terkini.
    Skor = jumlah kekerapan digit gabungan keempat-empat posisi — makin
    tinggi, makin "kuat" kombinasi itu berdasarkan corak terkini.

    Pulangkan `top_n` kombinasi teratas sebagai list of dict:
    {"Rank", "Nombor", "Lot", "Skor"}.
    """
    recent = draws[-recent_n:] if draws else []
    counters = [Counter() for _ in range(4)]
    for d in recent:
        num = f"{int(d['number']):04d}"
        for i in range(4):
            counters[i][num[i]] += 1

    scored = []
    for entry in combos:
        num, lot = entry.split("#####")
        score = sum(counters[i][num[i]] for i in range(4))
        scored.append((num, lot, score))

    scored.sort(key=lambda x: x[2], reverse=True)

    return [
        {"Rank": i + 1, "Nombor": num, "Lot": lot, "Skor": score}
        for i, (num, lot, score) in enumerate(scored[:top_n])
    ]


def backtest_wheelpick_topn(
    draws: list[dict],
    base_recent_n: int = 500,
    rank_range: tuple[int, int] = (4, 8),
    score_recent_n: int = 50,
    top_n: int = 100,
    rounds: int = 200,
    no_repeat: bool = False,
    no_triple: bool = False,
    no_pair: bool = False,
    no_ascend: bool = False,
    use_history: bool = False,
    sim_limit: int = 4,
    likes: list[str] | None = None,
    dislikes: list[str] | None = None,
) -> tuple[list[dict], dict]:
    """
    Backtest EMPIRIKAL untuk Wheelpick + Top-N (rank_combos): bagi setiap
    draw yang diuji, base DAN senarai kombinasi dijana HANYA drpd draw
    SEBELUM draw tersebut (kaedah "as of" — sama prinsip backtest_break
    dalam formula_break.py), supaya tiada maklumat masa depan bocor.

    Bagi draw yang base-nya match penuh (4/4 wujud dlm base — syarat
    perlu sebelum Top-N pun berpeluang tangkap nombor tu), semak sama
    ada nombor SEBENAR muncul dlm Top-N hasil rank_combos(). Turut kira
    baseline "rawak tulen" (top_n / saiz kolam SELEPAS tapis, bagi
    setiap draw) sebagai perbandingan adil — kalau recall sebenar
    hampir sama dgn baseline ni, formula skor semasa (atau apa-apa
    formula lain yg diuji dgn cara sama) tiada kelebihan sebenar
    berbanding cuma teka rawak dari kolam yang sama.

    Pulangkan (records, ringkasan):
      records   -- senarai per-draw (utk papar dlm jadual)
      ringkasan -- dict statistik keseluruhan
    """
    records = []
    base_full = 0
    hits = 0
    baseline_probs = []

    for i in range(1, rounds + 1):
        test_draw = draws[-i]
        past = draws[:-i]
        if len(past) < base_recent_n:
            break
        try:
            base = generate_break_base(past, base_recent_n, rank_range)
        except ValueError:
            continue

        actual = f"{int(test_draw['number']):04d}"
        is_base_full = all(check_against_base(actual, base))

        combos = generate_wheel_combos(base)
        filtered = filter_wheel_combos(
            combos, past, no_repeat, no_triple, no_pair, no_ascend,
            use_history, sim_limit, likes, dislikes,
        )
        if not filtered:
            continue

        top_results = rank_combos(filtered, past, recent_n=score_recent_n, top_n=top_n)
        in_top = actual in {r["Nombor"] for r in top_results}

        records.append({
            "Tarikh": test_draw["date"],
            "Nombor": test_draw["number"],
            "Base Penuh": "🎯 Ya" if is_base_full else "—",
            f"Masuk Top {top_n}": "✅" if in_top else ("—" if not is_base_full else "❌"),
            "Saiz Kolam": len(filtered),
        })

        if is_base_full:
            base_full += 1
            baseline_probs.append(min(top_n, len(filtered)) / len(filtered))
            if in_top:
                hits += 1

    records.reverse()

    recall_rate = round(hits / base_full * 100, 2) if base_full else 0.0
    baseline_rate = round(sum(baseline_probs) / len(baseline_probs) * 100, 2) if baseline_probs else 0.0

    ringkasan = {
        "draw_diuji": len(records),
        "base_penuh": base_full,
        "masuk_top_n": hits,
        "recall_rate": recall_rate,
        "baseline_rawak": baseline_rate,
        "kelebihan_vs_rawak": round(recall_rate - baseline_rate, 2),
    }
    return records, ringkasan


def pick_from_base(base: list[list[str]], index: int, arah: str = "kiri") -> str:
    """Pilih satu digit dari setiap P1–P4 pada posisi `index`, susun ikut `arah`."""
    if not (0 <= index < len(base[0])):
        raise IndexError("index di luar julat panjang base")

    if arah == "kiri":
        order = [0, 1, 2, 3]
    elif arah == "kanan":
        order = [3, 2, 1, 0]
    else:
        raise ValueError("arah mesti 'kiri' atau 'kanan'")

    return "".join(base[i][index] for i in order)
