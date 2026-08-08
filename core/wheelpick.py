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


def score_combos_by_style(
    combos: list[str],
    draws: list[dict],
    recent_n: int = 50,
    style: str = "sum",
    gap_window: int = 200,
) -> list[dict]:
    """
    Skor SEMUA kombinasi ("NNNN#####lot") ikut gaya skor pilihan.
    (rank_combos() asal kekal guna gaya "sum" & TAK disentuh — fungsi ni
    berasingan sepenuhnya, sekadar pilihan tambahan untuk dibandingkan.)

    style:
      "sum"       -- (sama seperti rank_combos asal) jumlah terus
                     kekerapan digit gabungan 4 posisi dlm `recent_n`
                     draw terkini.
      "geometric" -- min. geometrik (P1×P2×P3×P4)^0.25 -- penalti kuat
                     kalau ADA satu posisi lemah walaupun 3 posisi lain
                     panas (elak skor tinggi "palsu" drpd 1 posisi dominan).
      "voting"    -- kira berapa (0-4) posisi combo tu ada digit dlm
                     TOP-3 paling kerap utk posisi tersebut. Lebih mudah
                     difahami macam manusia ("3 drpd 4 digit panas").
                     Sekiranya seri, guna skor "sum" sbg tie-break.
      "overdue"   -- jumlah "gap" (bilangan draw sejak digit tu last
                     muncul kat posisi tersebut) merentas `gap_window`
                     draw terkini -- digit lama tak keluar dpt markah
                     lagi tinggi ("due utk keluar").

    Pulangkan SEMUA kombinasi (bukan cuma top_n) sbg list of dict
    {"Nombor", "Lot", "Skor"}, disusun MENURUN ikut skor — slice
    [:top_n] sendiri ikut keperluan.
    """
    if style not in ("sum", "geometric", "voting", "overdue"):
        raise ValueError("style mesti salah satu drpd: sum, geometric, voting, overdue")

    recent = draws[-recent_n:] if draws else []
    counters = [Counter() for _ in range(4)]
    for d in recent:
        num = f"{int(d['number']):04d}"
        for i in range(4):
            counters[i][num[i]] += 1

    top3 = None
    gaps = None
    if style == "voting":
        top3 = [{digit for digit, _ in counters[i].most_common(3)} for i in range(4)]
    elif style == "overdue":
        gaps = _compute_position_gaps(draws, gap_window)

    scored = []
    for entry in combos:
        num, lot = entry.split("#####")
        if style == "sum":
            s = sum(counters[i][num[i]] for i in range(4))
            sort_key, display = s, s
        elif style == "geometric":
            vals = [counters[i][num[i]] + 1 for i in range(4)]
            s = (vals[0] * vals[1] * vals[2] * vals[3]) ** 0.25
            sort_key, display = s, round(s, 2)
        elif style == "voting":
            votes = sum(1 for i in range(4) if num[i] in top3[i])
            tiebreak = sum(counters[i][num[i]] for i in range(4))
            sort_key, display = (votes, tiebreak), votes
        else:  # overdue
            s = sum(gaps[i][num[i]] for i in range(4))
            sort_key, display = s, s
        scored.append((num, lot, sort_key, display))

    scored.sort(key=lambda x: x[2], reverse=True)
    return [{"Nombor": num, "Lot": lot, "Skor": display} for num, lot, _, display in scored]


def _compute_position_gaps(draws: list[dict], gap_window: int) -> list[dict]:
    """Bagi setiap posisi (0-3), kira bilangan draw sejak setiap digit (0-9)
    last muncul, dlm `gap_window` draw terkini. Digit langsung tak muncul
    dlm tetingkap tu diberi gap maksimum (= panjang tetingkap)."""
    window = draws[-gap_window:] if draws else []
    L = len(window)
    gaps = [dict() for _ in range(4)]
    for i in range(4):
        seen = set()
        for offset, d in enumerate(reversed(window)):
            num = f"{int(d['number']):04d}"
            digit = num[i]
            if digit not in seen:
                gaps[i][digit] = offset
                seen.add(digit)
        for digit in "0123456789":
            if digit not in gaps[i]:
                gaps[i][digit] = L
    return gaps


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
    style: str = "sum",
    gap_window: int = 200,
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
    Backtest EMPIRIKAL untuk Wheelpick + Top-N: bagi setiap draw yang
    diuji, base DAN senarai kombinasi dijana HANYA drpd draw SEBELUM
    draw tersebut (kaedah "as of" — sama prinsip backtest_break dalam
    formula_break.py), supaya tiada maklumat masa depan bocor.

    Bagi draw yang base-nya match penuh (4/4 wujud dlm base — syarat
    perlu sebelum Top-N pun berpeluang tangkap nombor tu), semak sama
    ada nombor SEBENAR muncul dlm Top-N hasil `score_combos_by_style()`
    (gaya skor ikut parameter `style` — default "sum" = sama spt
    rank_combos() asal). Turut kira baseline "rawak tulen" (top_n /
    saiz kolam SELEPAS tapis, bagi setiap draw) sebagai perbandingan
    adil — kalau recall sebenar hampir sama dgn baseline ni, gaya skor
    yg diuji tiada kelebihan sebenar berbanding cuma teka rawak dari
    kolam yang sama.

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

        scored_all = score_combos_by_style(
            filtered, past, recent_n=score_recent_n, style=style, gap_window=gap_window,
        )
        top_results = scored_all[:top_n]
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


def recommend_top_n(
    draws: list[dict],
    top_n_candidates: list[int],
    base_recent_n: int = 500,
    rank_range: tuple[int, int] = (4, 8),
    score_recent_n: int = 50,
    rounds: int = 200,
    style: str = "sum",
    gap_window: int = 200,
    no_repeat: bool = False,
    no_triple: bool = False,
    no_pair: bool = False,
    no_ascend: bool = False,
    use_history: bool = False,
    sim_limit: int = 4,
    likes: list[str] | None = None,
    dislikes: list[str] | None = None,
) -> list[dict]:
    """
    Cadangan Top-N: bagi SETIAP top_n calon, jalankan backtest_wheelpick_topn
    (base, kolam & kaedah "as of" SAMA setiap kali — cuma Top-N yang berbeza),
    lalu banding recall sebenar vs baseline rawak tulen bagi Top-N tersebut.

    PENTING: recall MENTAH secara semula jadi naik bila Top-N makin besar
    (kolam yang diambil lagi besar = peluang lagi tinggi — bukan sebab
    "skor lebih pandai"). Sebab itu keputusan disusun ikut KELEBIHAN
    berbanding rawak (recall − baseline), BUKAN ikut recall mentah —
    supaya cadangan menunjukkan Top-N mana yang benar-benar dpt nilai
    tambah drpd formula skor, bukan sekadar Top-N yang paling besar.
    """
    results = []
    for n in sorted(set(top_n_candidates)):
        if n < 1:
            continue
        _, summary = backtest_wheelpick_topn(
            draws,
            base_recent_n=base_recent_n,
            rank_range=rank_range,
            score_recent_n=score_recent_n,
            top_n=n,
            rounds=rounds,
            style=style,
            gap_window=gap_window,
            no_repeat=no_repeat, no_triple=no_triple, no_pair=no_pair,
            no_ascend=no_ascend, use_history=use_history, sim_limit=sim_limit,
            likes=likes, dislikes=dislikes,
        )
        if summary["base_penuh"] == 0:
            continue
        results.append({
            "Top-N": n,
            "Base Penuh": summary["base_penuh"],
            "Masuk Top-N": summary["masuk_top_n"],
            "Recall (%)": summary["recall_rate"],
            "Baseline Rawak (%)": summary["baseline_rawak"],
            "Kelebihan vs Rawak": summary["kelebihan_vs_rawak"],
        })

    if not results:
        raise ValueError("Tiada Top-N berjaya diuji — cuba kurangkan rounds atau base_recent_n.")

    results.sort(key=lambda r: r["Kelebihan vs Rawak"], reverse=True)
    return results


def compare_scoring_styles(
    draws: list[dict],
    styles: list[str] | None = None,
    base_recent_n: int = 500,
    rank_range: tuple[int, int] = (4, 8),
    score_recent_n: int = 50,
    top_n: int = 100,
    rounds: int = 200,
    gap_window: int = 200,
    no_repeat: bool = False,
    no_triple: bool = False,
    no_pair: bool = False,
    no_ascend: bool = False,
    use_history: bool = False,
    sim_limit: int = 4,
    likes: list[str] | None = None,
    dislikes: list[str] | None = None,
) -> list[dict]:
    """
    Banding SEMUA gaya skor ("sum", "geometric", "voting", "overdue")
    pada N base, julat rank, Top-N & tetapan tapis yang SAMA — guna
    backtest_wheelpick_topn() bagi setiap gaya, susun ikut KELEBIHAN
    vs rawak (bukan recall mentah) supaya nampak gaya mana yg betul²
    ada nilai tambah, bukan sekadar kebetulan sampel kecil.
    """
    if styles is None:
        styles = ["sum", "geometric", "voting", "overdue"]

    results = []
    for style in styles:
        _, summary = backtest_wheelpick_topn(
            draws,
            base_recent_n=base_recent_n,
            rank_range=rank_range,
            score_recent_n=score_recent_n,
            top_n=top_n,
            rounds=rounds,
            style=style,
            gap_window=gap_window,
            no_repeat=no_repeat, no_triple=no_triple, no_pair=no_pair,
            no_ascend=no_ascend, use_history=use_history, sim_limit=sim_limit,
            likes=likes, dislikes=dislikes,
        )
        if summary["base_penuh"] == 0:
            continue
        results.append({
            "Gaya Skor": style,
            "Base Penuh": summary["base_penuh"],
            "Masuk Top-N": summary["masuk_top_n"],
            "Recall (%)": summary["recall_rate"],
            "Baseline Rawak (%)": summary["baseline_rawak"],
            "Kelebihan vs Rawak": summary["kelebihan_vs_rawak"],
        })

    if not results:
        raise ValueError("Tiada gaya skor berjaya diuji — cuba kurangkan rounds atau base_recent_n.")

    results.sort(key=lambda r: r["Kelebihan vs Rawak"], reverse=True)
    return results


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
