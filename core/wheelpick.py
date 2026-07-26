"""
core/wheelpick.py
-------------------
Wheelpick Generator: hasilkan & tapis kombinasi 4D daripada mana-mana
base 4-posisi (biasanya hasil Formula Break) mengikut pelbagai kriteria.
"""

import itertools
from collections import Counter


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
