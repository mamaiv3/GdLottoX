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
    Uji prestasi sebenar Formula Break (base tunggal) terhadap `rounds`
    draw yang lepas.

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


def backtest_combined(
    draws: list[dict],
    recent_n: int = DEFAULT_RECENT_N,
    rounds: int = 10,
    rank_range: tuple[int, int] = DEFAULT_RANK_RANGE,
) -> tuple[list[dict], int, float]:
    """
    Uji prestasi Base Gabungan (Hari Ini + Semalam) terhadap `rounds`
    draw yang lepas — konsep sama adil seperti `backtest_break`.

    Untuk draw yang diuji, "base hari ini" & "base semalam" kedua-duanya
    dijana HANYA daripada draw SEBELUM draw tersebut (base semalam guna
    satu draw lebih awal lagi), lalu digabungkan sebelum disemak.
    """
    records = []
    full_match = 0

    for i in range(1, rounds + 1):
        test_draw = draws[-i]
        past = draws[:-i]
        if len(past) < recent_n + 1:
            break
        try:
            base_today = generate_break_base(past, recent_n, rank_range)
            base_yesterday = generate_break_base(past[:-1], recent_n, rank_range)
            base = combine_bases(base_today, base_yesterday)
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


def scan_digit_history(
    draws: list[dict],
    target: list[str],
    recent_n: int = DEFAULT_RECENT_N,
    rank_range: tuple[int, int] = DEFAULT_RANK_RANGE,
    min_match: int = 1,
) -> list[dict]:
    """
    Imbas SEPANJANG sejarah draw: bagi setiap tarikh (bermula draw ke-
    (recent_n + 1)), jana base Formula Break guna draw SEBELUM tarikh
    tersebut sahaja (elak bocor maklumat masa depan), lalu semak `target`
    (4 digit, satu bagi setiap P1–P4) terhadap base tersebut.

    Pulangkan senarai rekod (tarikh, nombor draw sebenar, bilangan padanan,
    label kedudukan yang padan) bagi tarikh yang ada sekurang-kurangnya
    `min_match` padanan.
    """
    if len(target) != 4 or not all(len(t) == 1 and t.isdigit() for t in target):
        raise ValueError("Target mesti tepat 4 digit tunggal (P1–P4).")

    target_number = "".join(target)
    records = []
    for i in range(recent_n, len(draws)):
        past = draws[:i]
        try:
            base = generate_break_base(past, recent_n, rank_range)
        except ValueError:
            continue

        flags = check_against_base(target_number, base)
        match_count = sum(flags)
        if match_count >= min_match:
            label = "P1-P4" if match_count == 4 else " ".join(
                f"P{j + 1}" if flags[j] else "x" for j in range(4)
            )
            records.append({
                "Tarikh": draws[i]["date"],
                "Nombor Draw": draws[i]["number"],
                "Bilangan Padanan": match_count,
                "Kedudukan": label,
            })
    return records


def recommend_rank_range(
    draws: list[dict],
    target: list[str],
    recent_n: int = DEFAULT_RECENT_N,
    width: int = 5,
) -> list[dict]:
    """
    Cuba SEMUA julat rank yang lebar sama (`width`) dalam lingkungan 1–10,
    kira jumlah padanan digit `target` sepanjang sejarah bagi setiap julat
    (guna kaedah "as of" sama seperti `scan_digit_history` — tiada bocor
    maklumat masa depan), dan pulangkan keputusan tersusun (terbaik dahulu)
    supaya julat paling sepadan boleh dicadangkan.

    Lebar julat dikekalkan SAMA seperti tetapan semasa pengguna — supaya
    cadangan ini adil (julat lebih lebar semestinya ada lebih banyak digit
    calon, jadi tak boleh dibandingkan terus dgn julat lebih sempit).
    """
    if len(target) != 4 or not all(len(t) == 1 and t.isdigit() for t in target):
        raise ValueError("Target mesti tepat 4 digit tunggal (P1–P4).")

    width = max(1, min(10, width))
    target_number = "".join(target)

    results = []
    for start in range(1, 10 - width + 2):
        end = start + width - 1
        total_match = 0
        full_match = 0
        evaluated = 0
        for i in range(recent_n, len(draws)):
            past = draws[:i]
            try:
                base = generate_break_base(past, recent_n, (start, end))
            except ValueError:
                continue
            flags = check_against_base(target_number, base)
            total_match += sum(flags)
            if all(flags):
                full_match += 1
            evaluated += 1
        results.append({
            "Julat": f"R{start}-R{end}",
            "rank_range": (start, end),
            "Jumlah Padanan Digit": total_match,
            "Match Penuh (4/4)": full_match,
            "Draw Diuji": evaluated,
        })

    results.sort(key=lambda r: (r["Match Penuh (4/4)"], r["Jumlah Padanan Digit"]), reverse=True)
    return results
