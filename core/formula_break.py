"""
core/formula_break.py
----------------------
TERAS aplikasi ini: Formula Break.

Konsep:
Bagi setiap posisi (P1–P4), kira kekerapan setiap digit (0–9) dalam
N draw terkini, susun ikut rank 1 (paling kerap) hingga 10 (paling
jarang). Formula Break TIDAK ambil digit paling 'panas' (rank 1–5),
sebaliknya ambil digit rank ke-6 hingga ke-10 — andaian: digit yang
sudah 'sejuk' sedikit ini berpotensi untuk 'break' masuk giliran
seterusnya.
"""

from collections import Counter

DEFAULT_RECENT_N = 50
DEFAULT_RANK_RANGE = (6, 10)


def generate_break_base(
    draws: list[dict],
    recent_n: int = DEFAULT_RECENT_N,
    rank_range: tuple[int, int] = DEFAULT_RANK_RANGE,
) -> list[list[str]]:
    """Jana base 4-posisi (P1–P4) menggunakan Formula Break."""
    if len(draws) < recent_n:
        raise ValueError(f"Draw tidak mencukupi. Perlu {recent_n}, ada {len(draws)}.")

    rank_start, rank_end = rank_range
    recent = draws[-recent_n:]

    base = []
    for i in range(4):
        col_digits = [f"{int(d['number']):04d}"[i] for d in recent]
        ranked = Counter(col_digits).most_common(10)
        selected = [digit for digit, _ in ranked[rank_start - 1:rank_end]]
        base.append(selected)
    return base


def check_against_base(number: str, base: list[list[str]]) -> list[bool]:
    """Semak setiap digit satu nombor (4 aksara) terhadap base P1–P4."""
    digits = f"{int(number):04d}"
    return [digits[i] in base[i] for i in range(4)]


def combine_bases(base_a: list[list[str]], base_b: list[list[str]]) -> list[list[str]]:
    """
    Gabungkan dua base 4-posisi (cth: base hari ini + base semalam) jadi
    satu base gabungan.

    Bagi setiap posisi (P1–P4): digit dari `base_a` dikekalkan dahulu
    ikut susunan asal, diikuti digit dari `base_b` yang belum ada
    (tiada pendua). Cth: "12345" gabung "23456" -> "123456".
    """
    if len(base_a) != 4 or len(base_b) != 4:
        raise ValueError("Kedua-dua base mesti ada tepat 4 posisi (P1–P4).")

    combined = []
    for i in range(4):
        merged = list(dict.fromkeys(base_a[i]))  # kekal susunan asal, buang pendua dalaman
        for digit in base_b[i]:
            if digit not in merged:
                merged.append(digit)
        combined.append(merged)
    return combined


def backtest_break(
    draws: list[dict],
    recent_n: int = DEFAULT_RECENT_N,
    rounds: int = 10,
    rank_range: tuple[int, int] = DEFAULT_RANK_RANGE,
) -> tuple[list[dict], int, float]:
    """
    Uji prestasi sebenar Formula Break terhadap `rounds` draw yang lepas.

    Untuk setiap draw yang diuji, base dijana HANYA daripada draw
    SEBELUM draw tersebut — supaya tiada maklumat masa depan 'bocor'
    ke dalam ujian (fair backtest).
    """
    records = []
    full_match = 0

    for i in range(1, rounds + 1):
        test_draw = draws[-i]
        past = draws[:-i]
        if len(past) < recent_n:
            break
        try:
            base = generate_break_base(past, recent_n, rank_range)
        except ValueError:
            continue

        flags = check_against_base(test_draw["number"], base)
        is_full = all(flags)
        if is_full:
            full_match += 1

        records.append({
            "Tarikh": test_draw["date"],
            "Nombor": test_draw["number"],
            "P1": "✅" if flags[0] else "❌",
            "P2": "✅" if flags[1] else "❌",
            "P3": "✅" if flags[2] else "❌",
            "P4": "✅" if flags[3] else "❌",
            "Match Penuh": "🎯 Ya" if is_full else "—",
        })

    records.reverse()
    hit_rate = round(full_match / len(records) * 100, 2) if records else 0.0
    return records, full_match, hit_rate
