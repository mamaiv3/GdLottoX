"""
core/prediction_2d.py
-----------------------
Engine TOP 10 ramalan 2D untuk NEXT DRAW — ikut
TASK_TEKNIKAL_TOP10_2D_NEXT_DRAW.txt.

Definisi 2D (Seksyen C) — bagi 4 digit ABCD:
    P12 = AB   (2 digit pertama)
    P23 = BC   (digit tengah)
    P34 = CD   (2 digit terakhir)
    P14 = AD   (digit pertama + digit terakhir)

PENTING — apa fail ni BOLEH dan TAK BOLEH buat:
GD Lotto adalah draw rawak & bebas (independent) setiap kali — sebab itu
chi_square_uniformity() dalam formula_break.py wujud, untuk uji andaian
rawak tu secara empirik, bukan anggap sahaja. Semua 8 feature struktur
di bawah (frequency, recency, position, trend, gap, cluster, digit,
transition) mengukur CORAK SEJARAH sahaja. Bagi draw yang benar-benar
rawak, corak sejarah TIDAK membawa maklumat sebenar tentang draw akan
datang, walau secanggih mana pun engineering-nya. Walk-forward backtest
di bawah dibina untuk JUJUR mendedahkan ini berbanding baseline rawak
(lihat calculate_random_baseline) — bukan untuk "buktikan" sistem ni
berfungsi.

Reka bentuk fail ni sengaja EPAT: setiap fungsi feature adalah fungsi
TULEN (pure) drpd parameter `draws` yang diberi sahaja — tiada
state global/incremental merentasi panggilan. Ini menjamin sifat
"tiada future leakage" secara STRUKTUR (bukan sekadar dijaga dgn
teliti), dan mudah diaudit — rujuk test_no_future_leakage() dlm
tests/test_prediction_2d.py.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timezone

from core.formula_break import DEFAULT_RECENT_N

# ============================================================ CONSTANTS ===

WINDOW_SHORT = 10
WINDOW_MEDIUM = 30
WINDOW_LONG = 50
FEATURE_WINDOW = DEFAULT_RECENT_N  # window "recent" utk position/digit/transition (=50, ikut app sedia ada)

RECENCY_TAU = 15.0        # pemalar decay (draw) utk recency_score = exp(-gap/TAU)
GAP_CAP = 60               # cap gap (draw) supaya "lama tak keluar" tak mendominasi (Seksyen I)
CLUSTER_LOOKBACK = 20      # draw terkini dipertimbang utk cluster/momentum
CLUSTER_TAU = 5.0          # decay utk sumbangan setiap hit dlm cluster window

SHRINKAGE_ALPHA = 8.0      # alpha Bayesian smoothing hit-rate backtest (Seksyen W)
MIN_TRAIN_DRAWS = 60       # min draw sblm walk-forward backtest boleh mula (> WINDOW_LONG)

DIVERSITY_PENALTY_CAP = 0.12          # max 12% potongan skor (julat 10-15% dicadang Seksyen X)
DIVERSITY_FIRST_DIGIT_SOFT_LIMIT = 3  # bil. slot Top10 sebelum penalty digit-pertama bermula

BACKTEST_RECENT_FRACTION = 0.25  # sub-window "recent_bt" = 25% round backtest terkini (Seksyen S)
MIN_SAMPLE_FOR_FULL_SCORE = 5     # < ini, backtest_score di-cap (Seksyen V)
BACKTEST_SCORE_CAP_LOW_SAMPLE = 0.6

CANDIDATE_UNIVERSE_SIZE = 100

# Set weight cadangan — banding guna compare_weight_configs() (Seksyen U).
# NOTA PENTING: bahagian "backtest" hanya terpakai dlm MODE B (enable_backtest=True).
# Semasa walk-forward backtest itu SENDIRI (MODE A), backtest_score belum wujud
# (itulah yg cuba dikira), jadi generate_top10_base() renormalise 8 feature
# struktur sahaja bila enable_backtest=False — rujuk Seksyen O/AG.
WEIGHTS_V1 = {
    "frequency": 0.25, "recency": 0.10, "position": 0.10, "trend": 0.10,
    "gap": 0.05, "cluster": 0.10, "digit_pair": 0.05, "transition": 0.05,
    "backtest": 0.20,
}
WEIGHTS_V2 = {  # lebih berat pada backtest_score & frequency, kurang pada trend/gap spekulatif
    "frequency": 0.22, "recency": 0.08, "position": 0.10, "trend": 0.05,
    "gap": 0.03, "cluster": 0.07, "digit_pair": 0.05, "transition": 0.05,
    "backtest": 0.35,
}
WEIGHTS_V3 = {  # paling konservatif — nyaris hanya frequency + backtest
    "frequency": 0.35, "recency": 0.05, "position": 0.05, "trend": 0.05,
    "gap": 0.05, "cluster": 0.05, "digit_pair": 0.05, "transition": 0.05,
    "backtest": 0.30,
}
WEIGHT_CONFIGS = {"WEIGHTS_V1": WEIGHTS_V1, "WEIGHTS_V2": WEIGHTS_V2, "WEIGHTS_V3": WEIGHTS_V3}

FEATURE_KEYS = ("frequency", "recency", "position", "trend", "gap", "cluster", "digit_pair", "transition")


# ========================================================== C. DEFINISI 2D ===

def extract_2d(draw_4d: str) -> list[str]:
    """4 digit ABCD -> [P12, P23, P34, P14] = [AB, BC, CD, AD], string 2 aksara."""
    if not re.match(r"^\d{4}$", draw_4d):
        raise ValueError(f"draw_4d mesti tepat 4 digit (string), dapat: {draw_4d!r}")
    a, b, c, d = draw_4d
    return [a + b, b + c, c + d, a + d]


def build_2d_candidates() -> list[str]:
    """Candidate universe '00'..'99' — 100 nilai unik."""
    return [f"{i:02d}" for i in range(CANDIDATE_UNIVERSE_SIZE)]


ALL_CANDIDATES = build_2d_candidates()


# =============================================================== HELPERS ===

def _pairs(draw_number: str) -> list[str]:
    return extract_2d(draw_number)


def _minmax_normalize(raw: dict[str, float]) -> dict[str, float]:
    """Normalise dict {key: raw_value} kepada 0-1 (min-max). Neutral 0.5 kalau semua sama."""
    if not raw:
        return {}
    lo, hi = min(raw.values()), max(raw.values())
    if hi <= lo:
        return {k: 0.5 for k in raw}
    return {k: (v - lo) / (hi - lo) for k, v in raw.items()}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_and_clean_draws(draws: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Seksyen AI — validation sebelum formula. `load_draws()` sedia ada dlm
    core/data_draw.py sudah kuatkuasa format tarikh/4-digit semasa BACA
    fail (regex ketat), jadi di sini kita fokus pada apa yg BELUM dijamin:
    keteraturan susunan tarikh + duplicate date. Pulang (draws_bersih,
    senarai_amaran) — tak pernah "silently ignore".
    """
    warnings: list[str] = []
    seen: dict[str, dict] = {}
    order: list[str] = []
    for d in draws:
        date, number = d.get("date"), d.get("number")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date or "") or not re.match(r"^\d{4}$", number or ""):
            warnings.append(f"Draw tak sah diabaikan: {d!r}")
            continue
        if date in seen:
            if seen[date]["number"] != number:
                warnings.append(
                    f"Duplicate tarikh {date} dgn nombor berbeza ({seen[date]['number']} vs {number}) "
                    "— kekalkan yg PERTAMA dijumpai, abaikan yg kemudian."
                )
            else:
                warnings.append(f"Duplicate tarikh {date} (nombor sama) — dipadatkan jadi satu entri.")
            continue
        seen[date] = {"date": date, "number": number}
        order.append(date)

    cleaned = [seen[dt] for dt in sorted(order)]
    return cleaned, warnings


def _window_occurrence_counts(draws: list[dict], window: int | None) -> dict[str, int]:
    """
    Kiraan occurrence mentah setiap candidate merentasi SEMUA 4 slot
    (P12,P23,P34,P14) dlm `window` draw terkini (window=None -> semua draw
    yg diberi). Satu draw boleh sumbang 0-4 kiraan (bukan draw-level
    boolean) — ini "frequency" ikut slot, selari dgn Seksyen G (position)
    yg memecahkan jumlah ni ikut slot individu.
    """
    recent = draws if window is None else draws[-window:]
    counts: Counter = Counter()
    for d in recent:
        counts.update(_pairs(d["number"]))
    return {c: counts.get(c, 0) for c in ALL_CANDIDATES}


def _last_hit_gap(draws: list[dict]) -> dict[str, int]:
    """
    draws_since_last_hit bagi setiap candidate (draw-level: wujud di
    MANA-MANA slot dlm draw tsb = 1 hit, pendua dlm draw sama dikira
    sekali). Imbas draw TERKINI ke belakang, henti awal bila semua
    candidate dah dijumpai — cekap utk walk-forward merentasi ribuan
    draw. gap=0 bermaksud candidate wujud dlm draw TERAKHIR yg diberi.
    Tak pernah wujud langsung -> gap = len(draws) (di-cap oleh
    gap_score/recency_score, bukan dibiar tak terhingga).
    """
    n = len(draws)
    gap = {c: n for c in ALL_CANDIDATES}
    remaining = set(ALL_CANDIDATES)
    for offset, d in enumerate(reversed(draws)):
        if not remaining:
            break
        hits = set(_pairs(d["number"])) & remaining
        for c in hits:
            gap[c] = offset
        remaining -= hits
    return gap


# ==================================================== E. FEATURE 1 — FREQUENCY ===

def calculate_frequency_features(draws: list[dict]) -> dict[str, float]:
    """
    frequency_score = 0.40*norm(freq10) + 0.30*norm(freq30)
                     + 0.20*norm(freq50) + 0.10*norm(freq_all)
    """
    freq10 = _window_occurrence_counts(draws, WINDOW_SHORT)
    freq30 = _window_occurrence_counts(draws, WINDOW_MEDIUM)
    freq50 = _window_occurrence_counts(draws, WINDOW_LONG)
    freq_all = _window_occurrence_counts(draws, None)

    n10, n30 = _minmax_normalize(freq10), _minmax_normalize(freq30)
    n50, nall = _minmax_normalize(freq50), _minmax_normalize(freq_all)

    return {
        c: round(0.40 * n10[c] + 0.30 * n30[c] + 0.20 * n50[c] + 0.10 * nall[c], 6)
        for c in ALL_CANDIDATES
    }


# =============================================== F. FEATURE 2 — RECENCY / DECAY ===

def calculate_recency_features(draws: list[dict]) -> dict[str, float]:
    """recency_score = exp(-gap / RECENCY_TAU). Seksyen F."""
    gaps = _last_hit_gap(draws)
    return {c: round(math.exp(-gaps[c] / RECENCY_TAU), 6) for c in ALL_CANDIDATES}


# ============================================== G. FEATURE 3 — POSITION STRENGTH ===

def calculate_position_features(draws: list[dict], window: int = FEATURE_WINDOW) -> dict[str, dict]:
    """
    position_score = max(P12,P23,P34,P14 masing2 dinormalise) dgn bonus
    diversiti ringan (2D yg konsisten muncul di byk position dianggap
    lebih kukuh drpd yg hanya muncul di satu slot — Seksyen G).
    Pulang dict {candidate: {"score", "diversity", "slot_counts"}}.
    """
    recent = draws[-window:] if window else draws
    slot_names = ("P12", "P23", "P34", "P14")
    slot_counts = {c: {s: 0 for s in slot_names} for c in ALL_CANDIDATES}
    for d in recent:
        for slot, val in zip(slot_names, _pairs(d["number"])):
            slot_counts[val][slot] += 1

    norm_per_slot = {
        s: _minmax_normalize({c: slot_counts[c][s] for c in ALL_CANDIDATES})
        for s in slot_names
    }

    out = {}
    for c in ALL_CANDIDATES:
        slot_scores = [norm_per_slot[s][c] for s in slot_names]
        diversity = sum(1 for s in slot_names if slot_counts[c][s] > 0)
        bonus = 0.7 + 0.3 * (diversity / 4)
        out[c] = {
            "score": round(max(slot_scores) * bonus, 6),
            "diversity": diversity,
            "slot_counts": dict(slot_counts[c]),
        }
    return out


# ======================================================= H. FEATURE 4 — TREND ===

def calculate_trend_features(draws: list[dict]) -> dict[str, float]:
    """
    rate10=freq10/10, rate30=freq30/30, rate50=freq50/50
    trend_raw = 0.50*(rate10-rate30) + 0.30*(rate30-rate50) + 0.20*(rate10-rate50)
    -> min-max normalise merentasi 100 candidate.
    """
    freq10 = _window_occurrence_counts(draws, WINDOW_SHORT)
    freq30 = _window_occurrence_counts(draws, WINDOW_MEDIUM)
    freq50 = _window_occurrence_counts(draws, WINDOW_LONG)

    raw = {}
    for c in ALL_CANDIDATES:
        rate10 = freq10[c] / WINDOW_SHORT
        rate30 = freq30[c] / WINDOW_MEDIUM
        rate50 = freq50[c] / WINDOW_LONG
        raw[c] = 0.50 * (rate10 - rate30) + 0.30 * (rate30 - rate50) + 0.20 * (rate10 - rate50)
    return {c: round(v, 6) for c, v in _minmax_normalize(raw).items()}


# ================================================== I. FEATURE 5 — GAP / OVERDUE ===

def calculate_gap_features(draws: list[dict]) -> dict[str, float]:
    """
    gap_score = min(gap, GAP_CAP) / GAP_CAP — DI-CAP dgn sengaja & weight
    kecil (5% dlm WEIGHTS_V1). TIDAK bermaksud "lama tak keluar = mesti
    keluar" (gambler's fallacy) — hanya satu isyarat kecil di antara 9.
    """
    gaps = _last_hit_gap(draws)
    return {c: round(min(gaps[c], GAP_CAP) / GAP_CAP, 6) for c in ALL_CANDIDATES}


# ============================================ J. FEATURE 6 — CLUSTER / MOMENTUM ===

def calculate_cluster_features(
    draws: list[dict], lookback: int = CLUSTER_LOOKBACK, tau: float = CLUSTER_TAU,
) -> dict[str, float]:
    """
    Jumlah sumbangan exp-decay bagi SETIAP draw dlm `lookback` draw
    terkini yg mengandungi candidate (pendua dlm draw sama dikira SEKALI
    sahaja — keperluan eksplisit Seksyen J). Multi-hit yg rapat antara
    satu sama lain dlm tempoh terkini -> skor lebih tinggi drpd satu hit
    terpencil, walaupun gap purata sama.
    """
    recent = draws[-lookback:] if lookback else draws
    L = len(recent)
    raw = {c: 0.0 for c in ALL_CANDIDATES}
    for offset, d in enumerate(recent):
        age = (L - 1) - offset  # 0 = draw terakhir (paling baru)
        for c in set(_pairs(d["number"])):
            raw[c] += math.exp(-age / tau)
    return {c: round(v, 6) for c, v in _minmax_normalize(raw).items()}


# ============================================== K. FEATURE 7 — DIGIT STRENGTH ===

def calculate_digit_features(draws: list[dict], window: int = FEATURE_WINDOW) -> dict[str, float]:
    """
    digit_pair_score = average(norm(freq digit X), norm(freq digit Y))
    dikira drpd frequency digit 0-9 merentasi SEMUA 4 kolum digit mentah
    (P1-P4 nombor asal — BUKAN slot P12/P23/P34/P14) dlm `window` draw.
    """
    recent = draws[-window:] if window else draws
    digit_counts: Counter = Counter()
    for d in recent:
        digit_counts.update(d["number"])

    norm_digit = _minmax_normalize({str(x): digit_counts.get(str(x), 0) for x in range(10)})
    return {c: round((norm_digit[c[0]] + norm_digit[c[1]]) / 2, 6) for c in ALL_CANDIDATES}


# ============================================= L. FEATURE 8 — PAIR TRANSITION ===

def calculate_transition_features(draws: list[dict], window: int = FEATURE_WINDOW) -> dict[str, float]:
    """
    Kiraan berapa kali digit X diikuti SERTA-MERTA oleh digit Y, merentasi
    3 pasangan bersebelahan SEBENAR sahaja (P1->P2, P2->P3, P3->P4).
    P14 (pertama+akhir) SENGAJA tidak dikira di sini — ia bukan "transition"
    sebenar (tidak bersebelahan), walaupun ia satu slot sah utk extract_2d.
    """
    recent = draws[-window:] if window else draws
    counts: Counter = Counter()
    for d in recent:
        num = d["number"]
        counts[num[0] + num[1]] += 1
        counts[num[1] + num[2]] += 1
        counts[num[2] + num[3]] += 1
    raw = {c: counts.get(c, 0) for c in ALL_CANDIDATES}
    return {c: round(v, 6) for c, v in _minmax_normalize(raw).items()}


# ===================================================== FEATURE ORCHESTRATOR ===

def _compute_feature_matrix(draws: list[dict]) -> dict[str, dict]:
    """Kira SEMUA 8 feature struktur bagi `draws` yg diberi — fungsi tulen drpd draws sahaja."""
    freq = calculate_frequency_features(draws)
    rec = calculate_recency_features(draws)
    pos = calculate_position_features(draws)
    trend = calculate_trend_features(draws)
    gap = calculate_gap_features(draws)
    cluster = calculate_cluster_features(draws)
    digit = calculate_digit_features(draws)
    trans = calculate_transition_features(draws)
    raw_gaps = _last_hit_gap(draws)

    matrix = {}
    for c in ALL_CANDIDATES:
        matrix[c] = {
            "frequency": freq[c], "recency": rec[c], "position": pos[c]["score"],
            "trend": trend[c], "gap": gap[c], "cluster": cluster[c],
            "digit_pair": digit[c], "transition": trans[c],
            "position_diversity": pos[c]["diversity"],
            "current_gap": raw_gaps[c],
        }
    return matrix


# ================================================= X. DIVERSITY PENALTY (OPTIONAL) ===

def _apply_diversity_penalty(
    ranked: list[dict],
    cap: float = DIVERSITY_PENALTY_CAP,
    soft_limit: int = DIVERSITY_FIRST_DIGIT_SOFT_LIMIT,
) -> list[dict]:
    """
    Pilih 10 secara greedy drpd senarai tersusun ikut final_score. Kalau
    memilih satu candidate akan buat digit-pertama yg sama melebihi
    `soft_limit` slot dlm Top 10, skornya (utk pemilihan sahaja) dikurang
    sedikit — di-cap max `cap` (10-15% dicadang, kekal di 12%). TIDAK
    exclude candidate bagus, cuma kurangkan sedikit keutamaannya.
    """
    remaining = sorted(ranked, key=lambda r: r["final_score"], reverse=True)
    selected: list[dict] = []
    first_digit_counts: Counter = Counter()

    while remaining and len(selected) < 10:
        best_idx, best_adj = None, -1.0
        for i, cand in enumerate(remaining):
            fd = cand["number"][0]
            over = first_digit_counts[fd] + 1 - soft_limit
            penalty = min(cap, max(0, over) * (cap / 2))
            adj = cand["final_score"] * (1 - penalty)
            if adj > best_adj:
                best_adj, best_idx = adj, i
        chosen = remaining.pop(best_idx)
        chosen["diversity_adjusted_score"] = round(best_adj, 6)
        selected.append(chosen)
        first_digit_counts[chosen["number"][0]] += 1
    return selected


# ============================================== T/O. GENERATE TOP 10 (MODE A/B) ===

def generate_top10_base(
    draws: list[dict],
    weights: dict[str, float] = WEIGHTS_V1,
    enable_backtest: bool = False,
    backtest_scores: dict[str, dict] | None = None,
    apply_diversity: bool = True,
) -> list[dict]:
    """
    MODE A (enable_backtest=False): guna 8 feature struktur SAHAJA — dipanggil
    dari dalam run_walk_forward_backtest(). backtest_score belum wujud lagi
    di sini (itulah yg cuba dikira), jadi weight "backtest" dibuang & 8 weight
    struktur direnormalise ikut nisbah asal supaya jumlah kekal 1.0 — elak
    recursion (Seksyen O/AG).

    MODE B (enable_backtest=True): guna PENUH 9 feature termasuk backtest_score
    — perlukan `backtest_scores` drpd calculate_backtest_scores() yg dikira
    SEBELUM ini drpd walk-forward backtest yg sudah selesai.
    """
    if len(draws) < WINDOW_LONG:
        raise ValueError(f"Draw tidak mencukupi utk feature 2D. Perlu >= {WINDOW_LONG}, ada {len(draws)}.")

    matrix = _compute_feature_matrix(draws)

    if enable_backtest and backtest_scores:
        w = dict(weights)
    else:
        struct_total = sum(weights.get(k, 0.0) for k in FEATURE_KEYS) or 1.0
        w = {k: weights.get(k, 0.0) / struct_total for k in FEATURE_KEYS}
        w["backtest"] = 0.0

    scored = []
    for c in ALL_CANDIDATES:
        f = matrix[c]
        bt = (backtest_scores or {}).get(c, {})
        bt_score = bt.get("backtest_score", 0.0) if (enable_backtest and backtest_scores) else 0.0
        final = (
            w.get("frequency", 0.0) * f["frequency"]
            + w.get("recency", 0.0) * f["recency"]
            + w.get("position", 0.0) * f["position"]
            + w.get("trend", 0.0) * f["trend"]
            + w.get("gap", 0.0) * f["gap"]
            + w.get("cluster", 0.0) * f["cluster"]
            + w.get("digit_pair", 0.0) * f["digit_pair"]
            + w.get("transition", 0.0) * f["transition"]
            + w.get("backtest", 0.0) * bt_score
        )
        scored.append({
            "number": c,
            "final_score": round(final, 6),
            "frequency_score": f["frequency"],
            "recency_score": f["recency"],
            "position_score": f["position"],
            "trend_score": f["trend"],
            "gap_score": f["gap"],
            "cluster_score": f["cluster"],
            "digit_pair_score": f["digit_pair"],
            "transition_score": f["transition"],
            "backtest_score": round(bt_score, 6),
            "backtest_hit_rate": bt.get("hit_rate"),
            "backtest_hits": bt.get("times_hit"),
            "backtest_predictions": bt.get("times_predicted"),
            "historical_gap_rounds": bt.get("historical_gap_rounds"),
            "current_gap": f["current_gap"],
        })

    scored.sort(key=lambda r: r["final_score"], reverse=True)
    top10 = _apply_diversity_penalty(scored) if apply_diversity else scored[:10]
    for rank, r in enumerate(top10, start=1):
        r["rank"] = rank
    return top10


# ===================================================== N. WALK-FORWARD BACKTEST ===

def run_walk_forward_backtest(
    draws: list[dict],
    min_training_draws: int = MIN_TRAIN_DRAWS,
    test_rounds: int | None = None,
    weights: dict[str, float] = WEIGHTS_V1,
) -> list[dict]:
    """
    Utk setiap draw i (mula drpd min_training_draws hingga akhir):
        train  = draws[:i]      -- STRICTLY draw SEBELUM i sahaja
        actual = draws[i]       -- TIDAK PERNAH masuk dlm train
        prediction = generate_top10_base(train, ..., enable_backtest=False)
    Ini fair backtest walk-forward — tiada future leakage BY CONSTRUCTION,
    sebab train sentiasa satu slice list yg tamat sblm i (rujuk Seksyen N).
    """
    if len(draws) <= min_training_draws:
        return []

    start = min_training_draws
    end = len(draws)
    if test_rounds is not None:
        start = max(start, end - test_rounds)

    records = []
    for i in range(start, end):
        train = draws[:i]
        actual_draw = draws[i]
        prediction = generate_top10_base(train, weights, enable_backtest=False)
        predicted_numbers = [r["number"] for r in prediction]
        actual_2d = set(_pairs(actual_draw["number"]))
        hits = set(predicted_numbers) & actual_2d
        rank_of = {r["number"]: r["rank"] for r in prediction}

        records.append({
            "index": i,
            "date": actual_draw["date"],
            "actual_number": actual_draw["number"],
            "actual_2d": sorted(actual_2d),
            "predicted_top10": predicted_numbers,
            "hits": sorted(hits),
            "num_hits": len(hits),
            "hit_ranks": sorted(rank_of[h] for h in hits),
            "draw_hit": len(hits) > 0,
        })
    return records


# ========================================================== AC. BASELINE RAWAK ===

def _n_choose_k(n: int, k: int) -> int:
    return math.comb(n, k) if n >= k >= 0 else 0


def calculate_random_baseline(backtest_records: list[dict]) -> dict:
    """
    Baseline rawak TEPAT (formula probabilistik, BUKAN simulasi) — sama
    gaya dgn backtest_random_baseline() sedia ada dlm formula_break.py.
    Bagi setiap draw diuji, k = bil. 2D unik SEBENAR (1-4 selepas dedup).
    P(Top-10 RAWAK, 10 drpd 100 tanpa ganti, intersect >=1) =
        1 - C(100-k, 10) / C(100, 10)
    Jangkaan bil. hit (hypergeometric mean) = 10*k/100.
    """
    if not backtest_records:
        return {"evaluated": 0, "draws_with_hit_rate": 0.0, "average_hits_per_draw": 0.0}

    total = len(backtest_records)
    p_hit_sum = 0.0
    exp_hits_sum = 0.0
    denom = _n_choose_k(100, 10)
    for r in backtest_records:
        k = len(r["actual_2d"])
        p_hit = 1 - (_n_choose_k(100 - k, 10) / denom)
        p_hit_sum += p_hit
        exp_hits_sum += 10 * k / 100

    return {
        "evaluated": total,
        "draws_with_hit_rate": round(p_hit_sum / total * 100, 2),
        "average_hits_per_draw": round(exp_hits_sum / total, 4),
    }


# =================================================== Q/R/S/V/W. BACKTEST SCORES ===

def _per_candidate_backtest_stats(backtest_records: list[dict]) -> dict[str, dict]:
    stats = {
        c: {"times_predicted": 0, "times_hit": 0, "hit_ranks": [], "hit_round_indices": []}
        for c in ALL_CANDIDATES
    }
    for round_idx, r in enumerate(backtest_records):
        hit_set = set(r["hits"])
        rank_of = {num: rank for rank, num in enumerate(r["predicted_top10"], start=1)}
        for num in r["predicted_top10"]:
            s = stats[num]
            s["times_predicted"] += 1
            if num in hit_set:
                s["times_hit"] += 1
                s["hit_ranks"].append(rank_of[num])
                s["hit_round_indices"].append(round_idx)
    return stats


def calculate_backtest_scores(
    backtest_records: list[dict],
    alpha: float = SHRINKAGE_ALPHA,
    recent_fraction: float = BACKTEST_RECENT_FRACTION,
) -> dict[str, dict]:
    """
    backtest_score = 0.50*norm(smoothed_hit_rate) + 0.25*rank_quality
                    + 0.15*consistency + 0.10*norm(recent_bt_rate)

    - smoothed_hit_rate: shrinkage Bayesian drpd global rate (Seksyen W) —
      elak candidate dgn 1-2 sample kecil dpt skor ekstrem.
    - rank_quality: purata rank bila hit (rank 1 lebih baik drpd rank 10).
    - consistency: berapa stabil hit-rate antara separuh PERTAMA vs separuh
      KEDUA tempoh backtest (bukan hanya 1 "lucky streak").
    - recent_bt_rate: hit-rate dlm sub-tempoh TERKINI sahaja (25% round
      terakhir) — adakah ia "masih" berfungsi baru2 ni.
    - sample < 5 prediction: backtest_score di-cap (Seksyen V) — elak skor
      ekstrem drpd bilangan sample yg terlalu kecil utk bermakna.
    """
    if not backtest_records:
        return {
            c: {"backtest_score": 0.0, "hit_rate": 0.0, "raw_hit_rate": 0.0,
                "times_hit": 0, "times_predicted": 0, "average_rank": None, "best_rank": None}
            for c in ALL_CANDIDATES
        }

    stats = _per_candidate_backtest_stats(backtest_records)
    total_predictions = sum(s["times_predicted"] for s in stats.values())
    total_hits = sum(s["times_hit"] for s in stats.values())
    global_rate = (total_hits / total_predictions) if total_predictions else 0.0

    n_rounds = len(backtest_records)
    half = n_rounds // 2
    first_half = _per_candidate_backtest_stats(backtest_records[:half]) if half else {}
    second_half = _per_candidate_backtest_stats(backtest_records[half:]) if half else {}

    recent_cut = max(0, n_rounds - max(1, round(n_rounds * recent_fraction)))
    recent_stats = _per_candidate_backtest_stats(backtest_records[recent_cut:])

    smoothed, rank_quality, consistency, recent_rate = {}, {}, {}, {}

    for c in ALL_CANDIDATES:
        s = stats[c]
        tp, th = s["times_predicted"], s["times_hit"]
        smoothed[c] = (th + alpha * global_rate) / (tp + alpha)

        if th > 0:
            avg_rank = sum(s["hit_ranks"]) / th
            rank_quality[c] = max(0.0, min(1.0, (11 - avg_rank) / 10))
        else:
            rank_quality[c] = 0.0

        if half:
            fh, sh = first_half[c], second_half[c]
            fh_rate = (fh["times_hit"] + alpha * global_rate) / (fh["times_predicted"] + alpha)
            sh_rate = (sh["times_hit"] + alpha * global_rate) / (sh["times_predicted"] + alpha)
            diff = abs(fh_rate - sh_rate) / max(global_rate, 1e-6)
            consistency[c] = max(0.0, min(1.0, 1 - diff))
        else:
            consistency[c] = 0.5

        rs = recent_stats[c]
        recent_rate[c] = (rs["times_hit"] + alpha * global_rate) / (rs["times_predicted"] + alpha)

    norm_hit_rate = _minmax_normalize(smoothed)
    norm_recent = _minmax_normalize(recent_rate)

    out = {}
    for c in ALL_CANDIDATES:
        s = stats[c]
        bt_score = (
            0.50 * norm_hit_rate[c] + 0.25 * rank_quality[c]
            + 0.15 * consistency[c] + 0.10 * norm_recent[c]
        )
        if s["times_predicted"] < MIN_SAMPLE_FOR_FULL_SCORE:
            bt_score = min(bt_score, BACKTEST_SCORE_CAP_LOW_SAMPLE)

        avg_rank = (sum(s["hit_ranks"]) / s["times_hit"]) if s["times_hit"] else None
        last_hit_round = max(s["hit_round_indices"]) if s["hit_round_indices"] else None
        historical_gap = (n_rounds - 1 - last_hit_round) if last_hit_round is not None else None
        out[c] = {
            "backtest_score": round(bt_score, 6),
            "hit_rate": round(smoothed[c], 6),
            "raw_hit_rate": round(s["times_hit"] / s["times_predicted"], 6) if s["times_predicted"] else 0.0,
            "times_hit": s["times_hit"],
            "times_predicted": s["times_predicted"],
            "average_rank": round(avg_rank, 2) if avg_rank is not None else None,
            "best_rank": min(s["hit_ranks"]) if s["hit_ranks"] else None,
            "last_historical_hit_round": last_hit_round,
            "historical_gap_rounds": historical_gap,
        }
    return out


# ============================================================= U. WEIGHT COMPARE ===

def compare_weight_configs(
    draws: list[dict],
    configs: dict[str, dict] | None = None,
    min_training_draws: int = MIN_TRAIN_DRAWS,
) -> dict:
    """
    Bahagikan round walk-forward kpd VALIDATION (separuh awal, kronologi)
    & TEST (separuh akhir). Pilih config dgn validation hit-rate terbaik,
    lapor prestasi TEST config tsb sbg keputusan akhir — supaya pemilihan
    weight tidak "curang" (tuned) atas data yg sama yg dilaporkan (Seksyen U).
    """
    configs = configs or WEIGHT_CONFIGS
    per_config = {}
    for name, w in configs.items():
        records = run_walk_forward_backtest(draws, min_training_draws, None, w)
        n = len(records)
        if n < 4:
            per_config[name] = {"validation_hit_rate": 0.0, "test_hit_rate": 0.0, "rounds": n}
            continue
        half = n // 2
        val, test = records[:half], records[half:]
        val_rate = sum(1 for r in val if r["draw_hit"]) / len(val)
        test_rate = sum(1 for r in test if r["draw_hit"]) / len(test)
        per_config[name] = {
            "validation_hit_rate": round(val_rate * 100, 2),
            "test_hit_rate": round(test_rate * 100, 2),
            "rounds": n,
        }

    best_name = max(per_config, key=lambda k: per_config[k]["validation_hit_rate"]) if per_config else None
    return {"per_config": per_config, "selected_by_validation": best_name}


# ================================================= Z. TOP-LEVEL: NEXT DRAW TOP 10 ===

def generate_next_draw_top10(
    draws: list[dict],
    weights: dict[str, float] = WEIGHTS_V1,
    min_training_draws: int = MIN_TRAIN_DRAWS,
    test_rounds: int | None = None,
) -> dict:
    """
    Pipeline penuh (Seksyen AF):
      1. Walk-forward backtest atas SEMUA data sejarah (Mode A, tanpa backtest_score)
      2. Kira backtest_score terkalibrasi per-candidate drpd (1)
      3. Kira baseline rawak drpd round backtest yg SAMA (adil banding)
      4. Prediction akhir utk next draw (Mode B, guna PENUH 9 feature)
    """
    draws, warnings = validate_and_clean_draws(draws)

    if len(draws) < min_training_draws + 1:
        raise ValueError(
            f"Draw tidak mencukupi utk backtest+prediction. Perlu >= {min_training_draws + 1}, ada {len(draws)}."
        )

    bt_records = run_walk_forward_backtest(draws, min_training_draws, test_rounds, weights)
    bt_scores = calculate_backtest_scores(bt_records)
    baseline = calculate_random_baseline(bt_records)
    top10 = generate_top10_base(draws, weights, enable_backtest=True, backtest_scores=bt_scores)

    n = len(bt_records)
    draws_with_hit = sum(1 for r in bt_records if r["draw_hit"])
    total_hits = sum(r["num_hits"] for r in bt_records)
    total_actual_2d = sum(len(r["actual_2d"]) for r in bt_records)
    all_hit_ranks = sorted(rank for r in bt_records for rank in r["hit_ranks"])

    hit_rate = round((draws_with_hit / n * 100), 2) if n else 0.0
    avg_hits = round((total_hits / n), 4) if n else 0.0
    lift = round(hit_rate - baseline["draws_with_hit_rate"], 2) if n else None
    top10_recall = round(total_hits / total_actual_2d * 100, 2) if total_actual_2d else 0.0

    def _median(values: list[int]) -> float | None:
        if not values:
            return None
        mid = len(values) // 2
        return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2

    return {
        "generated_at": _now_iso(),
        "source_last_draw_date": draws[-1]["date"],
        "source_last_draw_number": draws[-1]["number"],
        "total_draws_used": len(draws),
        "data_warnings": warnings,
        "top10": top10,
        "backtest_summary": {
            "draws_tested": n,
            "draws_with_hit": draws_with_hit,
            "total_hits": total_hits,
            "hit_rate_pct": hit_rate,
            "average_hits_per_draw": avg_hits,
            "top10_recall_pct": top10_recall,
            "average_prediction_rank_when_hit": round(sum(all_hit_ranks) / len(all_hit_ranks), 2) if all_hit_ranks else None,
            "median_prediction_rank_when_hit": _median(all_hit_ranks),
            "best_rank": min(all_hit_ranks) if all_hit_ranks else None,
            "worst_rank": max(all_hit_ranks) if all_hit_ranks else None,
            "baseline_random_hit_rate_pct": baseline["draws_with_hit_rate"],
            "baseline_average_hits_per_draw": baseline["average_hits_per_draw"],
            "lift_vs_baseline_pct": lift,
        },
    }
