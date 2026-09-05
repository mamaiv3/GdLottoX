"""
app.py — Breakcode4D (versi ringkas)
--------------------------------------
Fokus penuh pada:
  1. Formula Break  — jana & uji base P1–P4
  2. Wheelpick      — jana & tapis kombinasi 4D
  3. Data Draw      — data sokongan (sejarah keputusan)
"""

import io
import random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from core.data_draw import (
    DRAW_FILE,
    add_draw,
    get_draw_countdown_from_last_8pm,
    load_draws,
    scrape_latest,
)
from core.formula_break import (
    DEFAULT_RANK_RANGE,
    DEFAULT_RECENT_N,
    backtest_break,
    backtest_combined,
    backtest_random_baseline,
    check_against_base,
    chi_square_uniformity,
    combine_bases,
    ensemble_stable_digits,
    generate_break_base,
    recommend_base_config,
    recommend_rank_range,
    recommend_rank_range_general,
    recommend_recent_n,
    scan_digit_history,
)
from core.prediction_2d import (
    MIN_TRAIN_DRAWS as P2D_MIN_TRAIN_DRAWS,
    WEIGHT_CONFIGS as P2D_WEIGHT_CONFIGS,
    compare_weight_configs,
    generate_next_draw_top10,
)
from core.wheelpick import (
    backtest_wheelpick_topn,
    compare_scoring_styles,
    filter_by_2d1d,
    filter_wheel_combos,
    generate_wheel_combos,
    get_like_dislike_digits,
    rank_combos,
    score_combos_by_style,
)

st.set_page_config(page_title="Breakcode4D — Formula Break", page_icon="🔮", layout="wide")

FONT_DIR = Path(__file__).parent / "assets" / "fonts"


# ============================================================== HELPERS ===
def load_css() -> None:
    css_path = Path(__file__).parent / "assets" / "style.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)


def card(label: str, value: str, css_class: str = "") -> str:
    return (
        f'<div class="bc4d-card"><div class="label">{label}</div>'
        f'<div class="value {css_class}">{value}</div></div>'
    )


def card_grid(cards_html: list[str], min_width: int = 118) -> str:
    return f'<div class="bc4d-grid" style="--min-card:{min_width}px">{"".join(cards_html)}</div>'


def chip(pos: str, digit: str, state: str = "") -> str:
    cls = f" {state}" if state else ""
    return f'<div class="bc4d-chip{cls}"><div class="pos">{pos}</div><div class="digit">{digit}</div></div>'


def chip_row(chips_html: list[str]) -> str:
    return f'<div class="bc4d-chip-row">{"".join(chips_html)}</div>'


def section_title(icon: str, text: str, subtitle: str = "") -> None:
    sub = f'<div class="bc4d-section-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="bc4d-section-title"><span class="icon">{icon}</span>'
        f'<span class="text">{text}</span></div>{sub}',
        unsafe_allow_html=True,
    )


def divider() -> None:
    st.markdown('<hr class="bc4d-divider" />', unsafe_allow_html=True)


def digit_chips(number: str, flags: list[bool]) -> None:
    chips = [chip(f"P{i + 1}", number[i], "hit" if flags[i] else "miss") for i in range(4)]
    st.markdown(chip_row(chips), unsafe_allow_html=True)


def gold_top10_card(top10: list[dict]) -> str:
    """Kad senarai Top 10 kombinasi bergaya gold/black, disusun ikut skor."""
    if not top10:
        return '<div class="gld-card"><div class="gld-caption">Tiada kombinasi untuk dipaparkan.</div></div>'

    max_score = max(r["Skor"] for r in top10) or 1
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    rows = []
    for r in top10:
        rank = r["Rank"]
        badge = medals.get(rank, str(rank))
        cls = f" gld-rank{rank}" if rank in medals else ""
        pct = round(r["Skor"] / max_score * 100)
        rows.append(
            f'<div class="gld-top-row{cls}">'
            f'<div class="gld-rank-badge">{badge}</div>'
            f'<div class="gld-top-main"><div class="gld-top-num">{r["Nombor"]}</div>'
            f'<div class="gld-bar-track"><div class="gld-bar-fill" style="width:{pct}%"></div></div></div>'
            f'<div class="gld-top-score"><div class="v">{r["Skor"]}</div><div class="l">{r["Lot"]}</div></div>'
            f"</div>"
        )
    return f'<div class="gld-card"><div class="gld-section-lbl">🏆 TOP 10 SET</div>{"".join(rows)}</div>'


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _center_text(draw: ImageDraw.ImageDraw, cx: int, y: int, text: str, font, fill, anchor: str = "mm") -> None:
    draw.text((cx, y), text, font=font, fill=fill, anchor=anchor)


def _rounded(draw: ImageDraw.ImageDraw, box, radius: int, **kwargs) -> None:
    draw.rounded_rectangle(box, radius=radius, **kwargs)


def _wrap_csv(draw: ImageDraw.ImageDraw, items: list[str], f, max_width: int, sep: str = ", ") -> list[str]:
    lines, cur = [], ""
    for it in items:
        cand = (cur + sep + it) if cur else it
        if draw.textlength(cand, font=f) <= max_width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = it
    if cur:
        lines.append(cur)
    return lines


def render_base_gold(
    base: list[list[str]],
    rank_start: int,
    rank_end: int,
    kombinasi: str,
    date_label: str,
    result_handle: str = "@Breakcode4d",
    hot_digits: set[str] | None = None,
    top10_numbers: list[str] | None = None,
) -> bytes:
    """Lukis kad 'Base Draw' (gold/black - design asal) sebagai PNG sebenar."""
    W, H = 1000, 1300
    GOLD = (212, 175, 55)
    GOLD_LT = (244, 226, 161)
    BG = (8, 6, 3)
    CREAM = (231, 220, 184)
    MUTED = (138, 124, 80)
    DARK_TXT = (18, 14, 6)
    hot = hot_digits or set()

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Subtle top glow
    glow = Image.new("L", (W, H), 0)
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse((W / 2 - 420, -420, W / 2 + 420, 420), fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    gold_layer = Image.new("RGB", (W, H), GOLD)
    img = Image.composite(gold_layer, img, glow)
    draw = ImageDraw.Draw(img)

    margin = 40
    _rounded(draw, (margin, margin, W - margin, H - margin), 28, outline=GOLD, width=3)

    f_ribbon = _font("Outfit-Bold.ttf", 30)
    f_date = _font("Outfit-Bold.ttf", 130)
    f_seal = _font("JetBrainsMono-Bold.ttf", 34)
    f_headline = _font("Outfit-Bold.ttf", 42)
    f_subline = _font("Outfit-Regular.ttf", 26)
    f_th = _font("Outfit-Bold.ttf", 34)
    f_rank = _font("JetBrainsMono-Regular.ttf", 24)
    f_cell = _font("JetBrainsMono-Bold.ttf", 44)
    f_combo_lbl = _font("Outfit-Bold.ttf", 28)
    f_combo_num = _font("JetBrainsMono-Bold.ttf", 56)
    f_caption = _font("Outfit-Regular.ttf", 22)
    f_result = _font("Outfit-Bold.ttf", 28)

    pad = 76
    y = 110

    # Ribbon
    ribbon_w, ribbon_h = 260, 54
    _rounded(draw, (pad, y, pad + ribbon_w, y + ribbon_h), 10, fill=GOLD_LT)
    _center_text(draw, pad + ribbon_w / 2, y + ribbon_h / 2 + 2, "BASE DRAW", f_ribbon, DARK_TXT)

    # Hero row: date + seal
    y += ribbon_h + 26
    draw.text((pad, y), date_label, font=f_date, fill=GOLD_LT, anchor="lt")
    seal_cx, seal_cy, seal_r = W - pad - 60, y + 55, 62
    draw.ellipse((seal_cx - seal_r, seal_cy - seal_r, seal_cx + seal_r, seal_cy + seal_r), outline=GOLD, width=4)
    _center_text(draw, seal_cx, seal_cy + 2, "4D", f_seal, GOLD_LT)

    y += 158
    draw.text((pad, y), "BREAKCODE BASE DRAW", font=f_headline, fill=GOLD_LT, anchor="lt")
    y += 54
    draw.text((pad, y), f"Formula Break \u00b7 rank {rank_start}\u2013{rank_end}", font=f_subline, fill=MUTED, anchor="lt")

    # ---- Table ----
    y += 50
    table_x0, table_x1 = pad, W - pad
    n_rows = max(len(p) for p in base)
    header_h = 66
    row_h = 78
    col_w = (table_x1 - table_x0 - 120) / 4
    lbl_w = 120

    _rounded(draw, (table_x0, y, table_x1, y + header_h), 12, fill=GOLD)
    labels = ["P1", "P2", "P3", "P4"]
    for i, lbl in enumerate(labels):
        cx = table_x0 + lbl_w + col_w * i + col_w / 2
        _center_text(draw, cx, y + header_h / 2 + 2, lbl, f_th, DARK_TXT)

    row_y = y + header_h
    badge_w, badge_h = 76, 60
    for row_i in range(n_rows):
        rank_no = rank_start + row_i
        cy = row_y + row_h / 2
        _center_text(draw, table_x0 + lbl_w / 2, cy + 2, f"R{rank_no}", f_rank, MUTED)
        for i, p in enumerate(base):
            digit = p[row_i] if row_i < len(p) else "\u2014"
            cx = table_x0 + lbl_w + col_w * i + col_w / 2
            if digit in hot:
                _rounded(
                    draw,
                    (cx - badge_w / 2, cy - badge_h / 2, cx + badge_w / 2, cy + badge_h / 2),
                    14, fill=GOLD_LT,
                )
                _center_text(draw, cx, cy + 2, digit, f_cell, DARK_TXT)
            else:
                _center_text(draw, cx, cy + 2, digit, f_cell, CREAM)
        draw.line((table_x0, row_y + row_h, table_x1, row_y + row_h), fill=(212, 175, 55, 40), width=1)
        row_y += row_h

    _rounded(draw, (table_x0, y, table_x1, row_y), 12, outline=GOLD, width=2)

    # ---- Kombinasi Utama band ----
    y = row_y + 30
    band_h = 90
    _rounded(draw, (table_x0, y, table_x1, y + band_h), 14, outline=GOLD, width=2)
    draw.text((table_x0 + 26, y + band_h / 2 + 2), "\U0001F3C6 Kombinasi Utama", font=f_combo_lbl, fill=MUTED, anchor="lm")
    draw.text((table_x1 - 26, y + band_h / 2 + 2), kombinasi, font=f_combo_num, fill=GOLD_LT, anchor="rm")

    # ---- Caption ----
    y += band_h + 24
    caption = "Base ikut corak statistik draw lepas sahaja \u2014 bukan jaminan keputusan."
    draw.text((table_x0, y), caption, font=f_caption, fill=MUTED, anchor="lt")
    y += 30
    draw.text((table_x0, y), "4D permainan nasib, mainlah secara bertanggungjawab.", font=f_caption, fill=MUTED, anchor="lt")

    # ---- Result pill ----
    y += 50
    pill_h = 64
    _rounded(draw, (table_x0, y, table_x1, y + pill_h), 32, outline=GOLD, width=2)
    _center_text(draw, (table_x0 + table_x1) / 2, y + pill_h / 2 + 2, f"\U0001F4E3 Result : {result_handle}", f_result, GOLD_LT)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- NEON ----
def render_base_neon(base, rank_start, rank_end, kombinasi, date_label, result_handle="@Breakcode4d", hot_digits=None, top10_numbers=None):
    hot = hot_digits or set()
    top10_numbers = top10_numbers or []
    W, H = 1000, 1300
    BG = (8, 6, 18)
    CYAN = (70, 245, 255)
    MAG = (255, 60, 200)
    CREAM = (222, 232, 240)
    MUTED = (110, 110, 150)

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for yy in range(0, H, 3):
        d.line((0, yy, W, yy), fill=(14, 11, 28), width=1)

    pad = 40
    d.rectangle((pad, pad, W - pad, H - pad), outline=MAG, width=2)
    d.rectangle((pad + 6, pad + 6, W - pad - 6, H - pad - 6), outline=CYAN, width=2)

    f_tag = _font("GeistMono-Bold.ttf", 24)
    f_date = _font("BigShoulders-Bold.ttf", 150)
    f_head = _font("BigShoulders-Bold.ttf", 40)
    f_sub = _font("GeistMono-Regular.ttf", 22)
    f_th = _font("GeistMono-Bold.ttf", 30)
    f_rank = _font("GeistMono-Regular.ttf", 22)
    f_cell = _font("GeistMono-Bold.ttf", 42)
    f_combo_lbl = _font("GeistMono-Bold.ttf", 26)
    f_combo_num = _font("BigShoulders-Bold.ttf", 60)
    f_cap = _font("GeistMono-Regular.ttf", 20)
    f_res = _font("GeistMono-Bold.ttf", 26)

    p = 76
    y = 100
    d.rectangle((p, y, p + 230, y + 44), outline=CYAN, width=2)
    _center_text(d, p + 115, y + 23, "[ BASE DRAW ]", f_tag, CYAN)
    y += 70
    d.text((p - 3, y - 3), date_label, font=f_date, fill=MAG, anchor="lt")
    d.text((p + 3, y + 3), date_label, font=f_date, fill=CYAN, anchor="lt")
    y += 168
    d.text((p, y), "BREAKCODE BASE DRAW", font=f_head, fill=CREAM, anchor="lt")
    y += 46
    d.text((p, y), f"Formula Break :: rank {rank_start}-{rank_end}", font=f_sub, fill=MUTED, anchor="lt")

    y += 46
    x0, x1 = p, W - p
    lbl_w = 116
    col_w = (x1 - x0 - lbl_w) / 4
    header_h, row_h = 60, 76
    d.rectangle((x0, y, x1, y + header_h), outline=CYAN, width=2)
    for i, lbl in enumerate(["P1", "P2", "P3", "P4"]):
        cx = x0 + lbl_w + col_w * i + col_w / 2
        _center_text(d, cx, y + header_h / 2 + 2, lbl, f_th, CYAN)
    ry = y + header_h
    n_rows = max(len(c) for c in base)
    for ri in range(n_rows):
        for k in range(0, int(x1 - x0), 14):
            d.line((x0 + k, ry + row_h, x0 + min(k + 7, x1 - x0), ry + row_h), fill=MAG, width=1)
        _center_text(d, x0 + lbl_w / 2, ry + row_h / 2 + 2, f"R{rank_start + ri}", f_rank, MUTED)
        for i, col in enumerate(base):
            digit = col[ri] if ri < len(col) else "-"
            cx = x0 + lbl_w + col_w * i + col_w / 2
            if digit in hot:
                bw, bh = 66, 56
                d.rectangle((cx - bw / 2, ry + row_h / 2 - bh / 2, cx + bw / 2, ry + row_h / 2 + bh / 2), outline=MAG, width=3)
                _center_text(d, cx, ry + row_h / 2 + 2, digit, f_cell, MAG)
            else:
                _center_text(d, cx, ry + row_h / 2 + 2, digit, f_cell, CREAM)
        ry += row_h
    d.rectangle((x0, y, x1, ry), outline=CYAN, width=2)

    y = ry + 26
    d.rectangle((x0, y, x1, y + 84), outline=MAG, width=2)
    d.text((x0 + 22, y + 42), "KOMBINASI UTAMA", font=f_combo_lbl, fill=MUTED, anchor="lm")
    d.text((x1 - 22, y + 42), f"[{kombinasi}]", font=f_combo_num, fill=CYAN, anchor="rm")

    y += 84 + 22
    d.text((x0, y), "// base ikut corak statistik draw lepas -- bukan jaminan.", font=f_cap, fill=MUTED, anchor="lt")
    y += 44
    d.rectangle((x0, y, x1, y + 58), outline=CYAN, width=2)
    _center_text(d, (x0 + x1) / 2, y + 29 + 2, f"> Result : {result_handle}_", f_res, CYAN)

    if top10_numbers:
        y += 58 + 26
        f_top_lbl = _font("GeistMono-Bold.ttf", 24)
        f_top_num = _font("GeistMono-Regular.ttf", 22)
        d.text((x0, y), "[ TOP 10 SET ]", font=f_top_lbl, fill=MAG, anchor="lt")
        y += 34
        for ln in _wrap_csv(d, top10_numbers, f_top_num, x1 - x0):
            d.text((x0, y), ln, font=f_top_num, fill=CREAM, anchor="lt")
            y += 30

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------- SWISS ----
def render_base_swiss(base, rank_start, rank_end, kombinasi, date_label, result_handle="@Breakcode4d", hot_digits=None, top10_numbers=None):
    hot = hot_digits or set()
    top10_numbers = top10_numbers or []
    W, H = 1000, 1260
    BG = (244, 241, 234)
    INK = (20, 20, 22)
    RED = (196, 42, 34)
    MUTED = (130, 126, 118)

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    f_tag = _font("WorkSans-Bold.ttf", 22)
    f_date = _font("Gloock-Regular.ttf", 150)
    f_head = _font("WorkSans-Bold.ttf", 30)
    f_sub = _font("WorkSans-Regular.ttf", 22)
    f_th = _font("WorkSans-Bold.ttf", 26)
    f_rank = _font("IBMPlexMono-Bold.ttf", 20)
    f_cell = _font("IBMPlexMono-Bold.ttf", 42)
    f_combo_lbl = _font("WorkSans-Bold.ttf", 22)
    f_combo_num = _font("Gloock-Regular.ttf", 64)
    f_cap = _font("WorkSans-Regular.ttf", 20)
    f_res = _font("WorkSans-Bold.ttf", 24)
    f_top_lbl = _font("WorkSans-Bold.ttf", 20)
    f_top_num = _font("IBMPlexMono-Bold.ttf", 22)

    p = 80
    y = 90
    d.rectangle((p, y, p + 6, y + 26), fill=RED)
    d.text((p + 20, y), "B A S E   D R A W", font=f_tag, fill=INK, anchor="lt")
    y += 50
    d.text((p, y), date_label, font=f_date, fill=INK, anchor="lt")
    y += 168
    d.text((p, y), "Breakcode Base Draw", font=f_head, fill=INK, anchor="lt")
    y += 40
    d.text((p, y), f"Formula Break \u00b7 rank {rank_start}\u2013{rank_end}", font=f_sub, fill=MUTED, anchor="lt")
    y += 40
    d.line((p, y, W - p, y), fill=INK, width=2)

    y += 30
    x0, x1 = p, W - p
    lbl_w = 100
    col_w = (x1 - x0 - lbl_w) / 4
    row_h = 74
    for i, lbl in enumerate(["P1", "P2", "P3", "P4"]):
        cx = x0 + lbl_w + col_w * i + col_w / 2
        _center_text(d, cx, y + 14, lbl, f_th, MUTED)
    y += 40
    d.line((x0, y, x1, y), fill=INK, width=1)
    n_rows = max(len(c) for c in base)
    for ri in range(n_rows):
        _center_text(d, x0 + lbl_w / 2, y + row_h / 2 + 2, f"R{rank_start + ri}", f_rank, MUTED)
        for i, col in enumerate(base):
            digit = col[ri] if ri < len(col) else "-"
            cx = x0 + lbl_w + col_w * i + col_w / 2
            cy = y + row_h / 2
            if digit in hot:
                _center_text(d, cx, cy + 2, digit, f_cell, RED)
                d.ellipse((cx - 5, cy + 34, cx + 5, cy + 44), fill=RED)
            else:
                _center_text(d, cx, cy + 2, digit, f_cell, INK)
        y += row_h
        d.line((x0, y, x1, y), fill=(210, 205, 194), width=1)

    y += 34
    d.text((x0, y), "KOMBINASI UTAMA", font=f_combo_lbl, fill=MUTED, anchor="lt")
    y += 30
    d.text((x0, y), kombinasi, font=f_combo_num, fill=RED, anchor="lt")

    y += 100
    d.line((x0, y, x1, y), fill=INK, width=2)
    y += 22
    cap = "Base ikut corak statistik draw lepas sahaja \u2014 bukan jaminan keputusan."
    d.text((x0, y), cap, font=f_cap, fill=MUTED, anchor="lt")
    y += 40
    d.ellipse((x0, y + 3, x0 + 10, y + 13), fill=RED)
    d.text((x0 + 22, y), f"Result : {result_handle}", font=f_res, fill=INK, anchor="lt")

    if top10_numbers:
        y += 46
        d.line((x0, y, x1, y), fill=(210, 205, 194), width=1)
        y += 20
        d.text((x0, y), "TOP 10 SET", font=f_top_lbl, fill=MUTED, anchor="lt")
        y += 30
        for ln in _wrap_csv(d, top10_numbers, f_top_num, x1 - x0):
            d.text((x0, y), ln, font=f_top_num, fill=INK, anchor="lt")
            y += 30

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# -------------------------------------------------------------- CASINO ----
def render_base_casino(base, rank_start, rank_end, kombinasi, date_label, result_handle="@Breakcode4d", hot_digits=None, top10_numbers=None):
    hot = hot_digits or set()
    top10_numbers = top10_numbers or []
    W, H = 1000, 1320
    BG = (7, 26, 20)
    GOLD = (206, 172, 84)
    GOLD_LT = (235, 214, 156)
    CREAM = (222, 232, 220)
    MUTED = (110, 140, 122)
    DARK = (8, 20, 15)

    img = Image.new("RGB", (W, H), BG)
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((W / 2 - 420, -350, W / 2 + 420, 350), fill=60)
    glow = glow.filter(ImageFilter.GaussianBlur(100))
    gl = Image.new("RGB", (W, H), (20, 60, 46))
    img = Image.composite(gl, img, glow)
    d = ImageDraw.Draw(img)

    p = 76
    _rounded(d, (p - 30, p - 30, W - p + 30, H - p + 30), 26, outline=GOLD, width=3)
    _rounded(d, (p - 22, p - 22, W - p + 22, H - p + 22), 20, outline=GOLD, width=1)
    for cx, cy in [(p - 30, p - 30), (W - p + 30, p - 30), (p - 30, H - p + 30), (W - p + 30, H - p + 30)]:
        d.regular_polygon((cx, cy, 12), n_sides=4, rotation=45, fill=GOLD)

    f_tag = _font("WorkSans-Bold.ttf", 24)
    f_date = _font("CrimsonPro-Bold.ttf", 130)
    f_head = _font("CrimsonPro-Bold.ttf", 40)
    f_sub = _font("WorkSans-Regular.ttf", 22)
    f_th = _font("WorkSans-Bold.ttf", 30)
    f_rank = _font("WorkSans-Regular.ttf", 20)
    f_cell = _font("RedHatMono-Bold.ttf", 42)
    f_combo_lbl = _font("WorkSans-Bold.ttf", 26)
    f_combo_num = _font("RedHatMono-Bold.ttf", 56)
    f_cap = _font("WorkSans-Regular.ttf", 20)
    f_res = _font("WorkSans-Bold.ttf", 26)
    f_top_lbl = _font("WorkSans-Bold.ttf", 22)
    f_top_num = _font("RedHatMono-Regular.ttf", 22)

    y = 110
    _rounded(d, (p, y, p + 260, y + 52), 26, fill=GOLD)
    _center_text(d, p + 130, y + 27, "\u2666 BASE DRAW \u2666", f_tag, DARK)
    y += 78
    d.text((p, y), date_label, font=f_date, fill=GOLD_LT, anchor="lt")
    y += 148
    d.text((p, y), "Breakcode Base Draw", font=f_head, fill=GOLD_LT, anchor="lt")
    y += 46
    d.text((p, y), f"Formula Break \u00b7 rank {rank_start}\u2013{rank_end}", font=f_sub, fill=MUTED, anchor="lt")

    y += 46
    x0, x1 = p, W - p
    lbl_w = 110
    col_w = (x1 - x0 - lbl_w) / 4
    header_h, row_h = 62, 76
    _rounded(d, (x0, y, x1, y + header_h), 10, fill=GOLD)
    for i, lbl in enumerate(["P1", "P2", "P3", "P4"]):
        cx = x0 + lbl_w + col_w * i + col_w / 2
        _center_text(d, cx, y + header_h / 2 + 2, lbl, f_th, DARK)
    ry = y + header_h
    n_rows = max(len(c) for c in base)
    for ri in range(n_rows):
        _center_text(d, x0 + lbl_w / 2, ry + row_h / 2 + 2, f"R{rank_start + ri}", f_rank, MUTED)
        for i, col in enumerate(base):
            digit = col[ri] if ri < len(col) else "-"
            cx = x0 + lbl_w + col_w * i + col_w / 2
            cy = ry + row_h / 2
            if digit in hot:
                r = 30
                d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=GOLD)
                _center_text(d, cx, cy + 2, digit, f_cell, DARK)
            else:
                _center_text(d, cx, cy + 2, digit, f_cell, CREAM)
        d.line((x0, ry + row_h, x1, ry + row_h), fill=GOLD, width=1)
        ry += row_h
    _rounded(d, (x0, y, x1, ry), 10, outline=GOLD, width=2)

    y = ry + 28
    _rounded(d, (x0, y, x1, y + 88), 14, outline=GOLD, width=2)
    d.text((x0 + 24, y + 44), "\u2660 Kombinasi Utama", font=f_combo_lbl, fill=MUTED, anchor="lm")
    d.text((x1 - 24, y + 44), kombinasi, font=f_combo_num, fill=GOLD_LT, anchor="rm")

    y += 88 + 24
    d.text((x0, y), "Base ikut corak statistik draw lepas sahaja \u2014 bukan jaminan.", font=f_cap, fill=MUTED, anchor="lt")
    y += 46
    _rounded(d, (x0, y, x1, y + 60), 30, outline=GOLD, width=2)
    _center_text(d, (x0 + x1) / 2, y + 30 + 2, f"\u2666 Result : {result_handle}", f_res, GOLD_LT)

    if top10_numbers:
        y += 60 + 26
        _center_text(d, (x0 + x1) / 2, y, "\u2666 TOP 10 SET \u2666", f_top_lbl, GOLD, anchor="ma")
        y += 32
        for ln in _wrap_csv(d, top10_numbers, f_top_num, x1 - x0):
            _center_text(d, (x0 + x1) / 2, y, ln, f_top_num, CREAM, anchor="ma")
            y += 30

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# -------------------------------------------------------------- TICKET ----
def render_base_ticket(base, rank_start, rank_end, kombinasi, date_label, result_handle="@Breakcode4d", hot_digits=None, top10_numbers=None):
    hot = hot_digits or set()
    top10_numbers = top10_numbers or []
    W, H = 1000, 1280
    BG = (233, 220, 195)
    INK = (46, 38, 30)
    RED = (168, 46, 40)
    NAVY = (34, 48, 70)
    MUTED = (140, 124, 96)

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    p = 46
    stub_x = p + 150
    d.rectangle((p, p, W - p, H - p), outline=INK, width=3)
    for yy in range(p, H - p, 22):
        d.ellipse((stub_x - 5, yy - 3, stub_x + 5, yy + 7), fill=BG, outline=INK, width=1)
    notch_r = 26
    d.ellipse((p - notch_r, H / 2 - notch_r, p + notch_r, H / 2 + notch_r), fill=BG, outline=INK, width=3)
    d.ellipse((W - p - notch_r, H / 2 - notch_r, W - p + notch_r, H / 2 + notch_r), fill=BG, outline=INK, width=3)

    # Jalur "barcode titik" menegak di ruang kosong tepi kiri (antara sempadan &
    # lubang gegelung) — meniru tanda di tepi tiket 4D sebenar. Lebar setiap bar
    # dikira drpd digit kombinasi + tarikh, jadi coraknya "terikat" dgn draw tsb.
    code_digits = "".join(ch for ch in f"{kombinasi}{date_label}{''.join(top10_numbers)}" if ch.isdigit()) or "0123456789"
    bar_x = p + 46
    bar_max_w = (stub_x - 5) - bar_x - 24
    bar_y = p + 18
    i = 0
    while bar_y < H - p - 18:
        dgt = int(code_digits[i % len(code_digits)])
        bw = 10 + dgt * (bar_max_w - 10) / 9
        bh = 5 if dgt % 2 == 0 else 3
        d.rectangle((bar_x, bar_y, bar_x + bw, bar_y + bh), fill=INK)
        bar_y += 11
        i += 1

    f_tag = _font("ArsenalSC-Regular.ttf", 24)
    f_date = _font("NationalPark-Bold.ttf", 130)
    f_head = _font("NationalPark-Bold.ttf", 34)
    f_sub = _font("WorkSans-Regular.ttf", 20)
    f_th = _font("ArsenalSC-Regular.ttf", 26)
    f_rank = _font("DMMono-Regular.ttf", 20)
    f_cell = _font("DMMono-Regular.ttf", 44)
    f_combo_lbl = _font("ArsenalSC-Regular.ttf", 22)
    f_combo_num = _font("NationalPark-Bold.ttf", 54)
    f_cap = _font("WorkSans-Regular.ttf", 19)
    f_res = _font("ArsenalSC-Regular.ttf", 24)
    f_top_lbl = _font("ArsenalSC-Regular.ttf", 22)
    f_top_num = _font("DMMono-Regular.ttf", 26)

    x0 = stub_x + 34
    x1 = W - p - 34
    y = 100
    d.ellipse((x1 - 110, y, x1, y + 66), outline=RED, width=3)
    _center_text(d, x1 - 55, y + 33 + 2, "BASE", f_tag, RED)
    d.text((x0, y), date_label, font=f_date, fill=NAVY, anchor="lt")
    y += 150
    d.text((x0, y), "Breakcode Base Draw", font=f_head, fill=INK, anchor="lt")
    y += 40
    d.text((x0, y), f"Formula Break \u00b7 rank {rank_start}\u2013{rank_end}", font=f_sub, fill=MUTED, anchor="lt")
    y += 30
    for xx in range(int(x0), int(x1), 14):
        d.line((xx, y, xx + 7, y), fill=INK, width=2)

    y += 26
    lbl_w = 96
    col_w = (x1 - x0 - lbl_w) / 4
    row_h = 74
    for i, lbl in enumerate(["P1", "P2", "P3", "P4"]):
        cx = x0 + lbl_w + col_w * i + col_w / 2
        _center_text(d, cx, y + 14, lbl, f_th, NAVY)
    y += 40
    n_rows = max(len(c) for c in base)
    for ri in range(n_rows):
        _center_text(d, x0 + lbl_w / 2, y + row_h / 2 + 2, f"R{rank_start + ri}", f_rank, MUTED)
        for i, col in enumerate(base):
            digit = col[ri] if ri < len(col) else "-"
            cx = x0 + lbl_w + col_w * i + col_w / 2
            cy = y + row_h / 2
            if digit in hot:
                d.ellipse((cx - 30, cy - 26, cx + 30, cy + 26), outline=RED, width=4)
            _center_text(d, cx, cy + 2, digit, f_cell, NAVY)
        y += row_h
        for xx in range(int(x0), int(x1), 14):
            d.line((xx, y, xx + 7, y), fill=(190, 178, 156), width=1)

    y += 24
    d.text((x0, y), "WINNING BASE NO.", font=f_combo_lbl, fill=MUTED, anchor="lt")
    y += 30
    d.text((x0, y), kombinasi, font=f_combo_num, fill=RED, anchor="lt")

    y += 90
    for xx in range(int(x0), int(x1), 14):
        d.line((xx, y, xx + 7, y), fill=INK, width=2)
    y += 20
    cap = "Base ikut corak statistik draw lepas sahaja \u2014 bukan jaminan keputusan."
    d.text((x0, y), cap, font=f_cap, fill=MUTED, anchor="lt")
    y += 36
    _center_text(d, (x0 + x1) / 2, y + 14, f"Result : {result_handle}", f_res, RED)

    if top10_numbers:
        y += 50
        for xx in range(int(x0), int(x1), 14):
            d.line((xx, y, xx + 7, y), fill=INK, width=1)
        y += 20
        _center_text(d, (x0 + x1) / 2, y, "TOP 10 SET", f_top_lbl, MUTED, anchor="ma")
        y += 36
        for ln in _wrap_csv(d, top10_numbers, f_top_num, x1 - x0):
            _center_text(d, (x0 + x1) / 2, y, ln, f_top_num, NAVY, anchor="ma")
            y += 34

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- SOFT ----
def render_base_soft(base, rank_start, rank_end, kombinasi, date_label, result_handle="@Breakcode4d", hot_digits=None, top10_numbers=None):
    hot = hot_digits or set()
    top10_numbers = top10_numbers or []
    W, H = 1000, 1320
    BG = (35, 27, 51)
    SHADOW_D = (24, 18, 38)
    SHADOW_L = (48, 38, 68)
    LAV = (200, 190, 230)
    PEACH = (245, 190, 160)
    MINT = (170, 220, 200)
    MUTED = (150, 140, 175)

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    p = 50
    _rounded(d, (p + 6, p + 8, W - p + 6, H - p + 8), 46, fill=SHADOW_D)
    _rounded(d, (p - 6, p - 6, W - p - 6, H - p - 6), 46, fill=SHADOW_L)
    _rounded(d, (p, p, W - p, H - p), 44, fill=BG)

    f_tag = _font("Outfit-Bold.ttf", 24)
    f_date = _font("BricolageGrotesque-Bold.ttf", 128)
    f_head = _font("BricolageGrotesque-Bold.ttf", 36)
    f_sub = _font("Outfit-Regular.ttf", 22)
    f_th = _font("Outfit-Bold.ttf", 28)
    f_rank = _font("Outfit-Regular.ttf", 20)
    f_cell = _font("RedHatMono-Bold.ttf", 40)
    f_combo_lbl = _font("Outfit-Bold.ttf", 24)
    f_combo_num = _font("RedHatMono-Bold.ttf", 52)
    f_cap = _font("Outfit-Regular.ttf", 20)
    f_res = _font("Outfit-Bold.ttf", 26)
    f_top_lbl = _font("Outfit-Bold.ttf", 20)
    f_top_num = _font("RedHatMono-Regular.ttf", 20)

    pad = 96
    y = 130
    _rounded(d, (pad, y, pad + 230, y + 52), 26, fill=LAV)
    _center_text(d, pad + 115, y + 27, "Base Draw", f_tag, (40, 32, 58))
    y += 78
    d.text((pad, y), date_label, font=f_date, fill=PEACH, anchor="lt")
    y += 146
    d.text((pad, y), "Breakcode Base Draw", font=f_head, fill=LAV, anchor="lt")
    y += 42
    d.text((pad, y), f"Formula Break \u00b7 rank {rank_start}\u2013{rank_end}", font=f_sub, fill=MUTED, anchor="lt")

    y += 50
    x0, x1 = pad, W - pad
    lbl_w = 90
    col_w = (x1 - x0 - lbl_w) / 4
    row_h = 70
    n_rows = max(len(c) for c in base)
    for i, lbl in enumerate(["P1", "P2", "P3", "P4"]):
        cx = x0 + lbl_w + col_w * i + col_w / 2
        _center_text(d, cx, y - 6, lbl, f_th, MUTED)
    y += 28
    for ri in range(n_rows):
        _center_text(d, x0 + lbl_w / 2, y + row_h / 2 + 2, f"R{rank_start + ri}", f_rank, MUTED)
        for i, col in enumerate(base):
            digit = col[ri] if ri < len(col) else "-"
            cx = x0 + lbl_w + col_w * i + col_w / 2
            cy = y + row_h / 2
            chip_w, chip_h = col_w - 16, row_h - 14
            box = (cx - chip_w / 2, cy - chip_h / 2, cx + chip_w / 2, cy + chip_h / 2)
            if digit in hot:
                _rounded(d, (box[0] + 3, box[1] + 4, box[2] + 3, box[3] + 4), 16, fill=SHADOW_D)
                _rounded(d, box, 16, fill=PEACH)
                _center_text(d, cx, cy + 2, digit, f_cell, (40, 24, 20))
            else:
                _rounded(d, box, 16, fill=SHADOW_L)
                _center_text(d, cx, cy + 2, digit, f_cell, MINT)
        y += row_h + 6

    y += 10
    _rounded(d, (x0 + 4, y + 4, x1 + 4, y + 90 + 4), 24, fill=SHADOW_D)
    _rounded(d, (x0, y, x1, y + 90), 24, fill=SHADOW_L)
    d.text((x0 + 26, y + 45), "Kombinasi Utama", font=f_combo_lbl, fill=MUTED, anchor="lm")
    d.text((x1 - 26, y + 45), kombinasi, font=f_combo_num, fill=PEACH, anchor="rm")

    y += 90 + 16
    cap = "Base ikut corak statistik draw lepas sahaja \u2014 bukan jaminan keputusan."
    d.text((x0, y), cap, font=f_cap, fill=MUTED, anchor="lt")
    y += 36
    _rounded(d, (x0, y, x1, y + 58), 29, fill=SHADOW_L)
    _center_text(d, (x0 + x1) / 2, y + 29 + 2, f"Result : {result_handle}", f_res, LAV)

    if top10_numbers:
        y += 58 + 20
        d.text((x0, y), "Top 10 Set", font=f_top_lbl, fill=MUTED, anchor="lt")
        y += 26
        for ln in _wrap_csv(d, top10_numbers, f_top_num, x1 - x0):
            d.text((x0, y), ln, font=f_top_num, fill=MINT, anchor="lt")
            y += 25

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------------------- CLASSIC ----
def _gen_classic_numbers(pool_numbers: list[str] | None = None) -> tuple[list[str], list[str], list[str]]:
    """Susun nombor utk kad gaya 'Classic Result':
    - Kalau `pool_numbers` (nombor SEBENAR drpd Wheelpick/Formula Break utk
      Base & tarikh draw semasa, disusun ikut skor) ada sekurang2nya 23 entri
      unik, GUNA terus 23 teratas tu — supaya kad ni SELARI dgn Base hari
      tersebut (bukan nombor lain yg tak berkaitan).
    - Kalau data x cukup (jarang berlaku), fallback rawak penuh 0000-9999
      supaya kad tetap boleh dijana.
    13 nombor teratas jadi 'Special pool'; 3 drpd 13 tu dipilih RAWAK jadi
    'Top Pick 1st/2nd/3rd' (kedudukan mana yg 'naik' sahaja yg rawak, bukan
    nombor²nya); baki 10 dipaparkan sbg 'Special'; 10 seterusnya jadi
    'Consolation'.
    """
    unique_pool = list(dict.fromkeys(pool_numbers or []))  # buang duplikat, kekalkan urutan skor
    if len(unique_pool) >= 23:
        chosen = unique_pool[:23]
        special_pool, consolation_pool = chosen[:13], chosen[13:23]
    else:
        rand_pool = [f"{n:04d}" for n in random.sample(range(10000), 23)]
        special_pool, consolation_pool = rand_pool[:13], rand_pool[13:]

    base_trio = set(random.sample(special_pool, 3))
    base_numbers = [n for n in special_pool if n in base_trio]
    special_numbers = [n for n in special_pool if n not in base_trio]
    return base_numbers, special_numbers, consolation_pool


def render_base_classic(
    date_label: str,
    result_handle: str = "@Breakcode4d",
    full_date=None,
    pool_numbers: list[str] | None = None,
) -> bytes:
    """Kad gaya 'keputusan klasik' (ilham papan 4D biasa — 1st/2nd/3rd + Special +
    Consolation) tapi dibrandkan Breakcode 4D & label ditukar jadi 'Top Pick 1st/2nd/3rd'
    (sbb bukan keputusan rasmi). Nombor diambil drpd skor Wheelpick/Formula
    Break SEBENAR utk Base semasa (bukan rawak) — lihat _gen_classic_numbers().
    """
    W, H = 1000, 1550
    RED = (196, 30, 37)
    DARK = (24, 24, 24)
    WHITE = (255, 255, 255)
    GRAY_LINE = (210, 210, 210)
    MUTED = (120, 120, 120)
    BLACK_TXT = (20, 20, 20)

    base_numbers, special_numbers, consolation_numbers = _gen_classic_numbers(pool_numbers)

    img = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)

    margin = 36
    _rounded(draw, (margin, margin, W - margin, H - margin), 20, outline=GRAY_LINE, width=2)

    f_brand = _font("Outfit-Bold.ttf", 44)
    f_seal = _font("Outfit-Bold.ttf", 30)
    f_date = _font("Outfit-Regular.ttf", 26)
    f_section = _font("Outfit-Bold.ttf", 26)
    f_label = _font("Outfit-Bold.ttf", 22)
    f_num_big = _font("JetBrainsMono-Bold.ttf", 50)
    f_num_grid = _font("JetBrainsMono-Bold.ttf", 32)
    f_dash = _font("JetBrainsMono-Bold.ttf", 28)
    f_caption = _font("Outfit-Regular.ttf", 20)
    f_pill = _font("Outfit-Bold.ttf", 24)

    inner_x0, inner_x1 = margin + 20, W - margin - 20
    table_x0, table_x1 = inner_x0, inner_x1

    # ---- Header (red band, brand) ----
    header_y0 = margin + 16
    header_h = 140
    header_y1 = header_y0 + header_h
    _rounded(draw, (inner_x0, header_y0, inner_x1, header_y1), 18, fill=RED)

    seal_cx, seal_cy, seal_r = inner_x0 + 90, (header_y0 + header_y1) / 2, 50
    draw.ellipse((seal_cx - seal_r, seal_cy - seal_r, seal_cx + seal_r, seal_cy + seal_r), fill=WHITE)
    _center_text(draw, seal_cx, seal_cy + 2, "4D", f_seal, RED)
    draw.text(
        (seal_cx + 90, (header_y0 + header_y1) / 2 + 2), "Breakcode 4D",
        font=f_brand, fill=WHITE, anchor="lm",
    )

    # ---- Date ----
    y = header_y1 + 30
    if full_date is not None:
        try:
            date_str = f"{full_date.strftime('%d-%m-%Y')} ({full_date.strftime('%a')})"
        except Exception:
            date_str = date_label
    else:
        date_str = date_label
    draw.text((inner_x0, y), f"Date: {date_str}", font=f_date, fill=BLACK_TXT, anchor="lt")

    # ---- Top Pick table (3 baris — GANTI label 1st/2nd/3rd Prize) ----
    y += 54
    row_h = 96
    label_w = 340
    table_top = y
    base_labels = ["Top Pick 1st", "Top Pick 2nd", "Top Pick 3rd"]
    for i, (lbl, num) in enumerate(zip(base_labels, base_numbers)):
        ry0 = table_top + i * row_h
        ry1 = ry0 + row_h
        draw.rectangle((table_x0, ry0, table_x0 + label_w, ry1), fill=DARK)
        _center_text(draw, table_x0 + label_w / 2, (ry0 + ry1) / 2 + 2, lbl, f_label, WHITE)
        draw.rectangle((table_x0 + label_w, ry0, table_x1, ry1), outline=GRAY_LINE, width=2)
        _center_text(draw, (table_x0 + label_w + table_x1) / 2, (ry0 + ry1) / 2 + 2, num, f_num_big, BLACK_TXT)
    table_bottom = table_top + row_h * 3
    draw.rectangle((table_x0, table_top, table_x1, table_bottom), outline=GRAY_LINE, width=2)

    def _section(y_start: float, title: str, numbers: list[str], blanks_mask, rows: int, cols: int) -> float:
        sy0 = y_start
        sh = 56
        draw.rectangle((table_x0, sy0, table_x1, sy0 + sh), fill=DARK)
        _center_text(draw, (table_x0 + table_x1) / 2, sy0 + sh / 2 + 2, title, f_section, WHITE)
        grid_y0 = sy0 + sh
        cell_w = (table_x1 - table_x0) / cols
        cell_h = 100
        idx = 0
        for r in range(rows):
            for c in range(cols):
                cx0, cx1 = table_x0 + c * cell_w, table_x0 + (c + 1) * cell_w
                cy0, cy1 = grid_y0 + r * cell_h, grid_y0 + (r + 1) * cell_h
                filled = blanks_mask[r][c] if blanks_mask else True
                draw.rectangle((cx0, cy0, cx1, cy1), outline=GRAY_LINE, width=1)
                if filled:
                    _center_text(draw, (cx0 + cx1) / 2, (cy0 + cy1) / 2 + 2, numbers[idx], f_num_grid, BLACK_TXT)
                    idx += 1
                else:
                    _center_text(draw, (cx0 + cx1) / 2, (cy0 + cy1) / 2 + 2, "----", f_dash, MUTED)
        return grid_y0 + rows * cell_h

    # ---- Special: 10 dipaparkan (13 dijana, 3 dah "naik" jadi Top Pick) ----
    y = table_bottom + 30
    special_mask = [[0, 1, 1, 1, 0], [1, 1, 1, 0, 1], [0, 1, 1, 1, 0]]
    y = _section(y, "SPECIAL", special_numbers, special_mask, rows=3, cols=5)

    # ---- Consolation: 10, grid penuh ----
    y += 30
    y = _section(y, "CONSOLATION", consolation_numbers, None, rows=2, cols=5)

    # ---- Caption / disclaimer (konsisten dgn style lain dlm app ni, word-wrap ikut lebar kad) ----
    y += 34
    caption_1 = (
        "Top Pick & Special ikut skor corak Formula Break/Wheelpick semasa \u2014 "
        "bukan keputusan rasmi mana-mana loteri."
    )
    caption_2 = "4D permainan nasib, mainlah secara bertanggungjawab."
    for line in _wrap_csv(draw, caption_1.split(" "), f_caption, table_x1 - table_x0, sep=" "):
        draw.text((table_x0, y), line, font=f_caption, fill=MUTED, anchor="lt")
        y += 26
    for line in _wrap_csv(draw, caption_2.split(" "), f_caption, table_x1 - table_x0, sep=" "):
        draw.text((table_x0, y), line, font=f_caption, fill=MUTED, anchor="lt")
        y += 26

    # ---- Result handle pill ----
    y += 20
    pill_h = 58
    _rounded(draw, (table_x0, y, table_x1, y + pill_h), 29, outline=DARK, width=2)
    _center_text(draw, (table_x0 + table_x1) / 2, y + pill_h / 2 + 2, f"Result Channel: {result_handle}", f_pill, DARK)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _draws_cache_key(draws: list[dict]) -> tuple:
    """Kunci cache mudah drpd senarai draws — cukup sbb draws hanya berubah bila fail draws.txt berubah."""
    return (len(draws), draws[-1]["date"] if draws else None, draws[-1]["number"] if draws else None)


@st.cache_data(show_spinner=False)
def _cached_scan_digit_history(_draws, cache_key, target, recent_n, rank_range, min_match):
    return scan_digit_history(_draws, target, recent_n=recent_n, rank_range=rank_range, min_match=min_match)


@st.cache_data(show_spinner="Mengira cadangan julat base...")
def _cached_recommend_rank_range(_draws, cache_key, target, recent_n, width):
    return recommend_rank_range(_draws, target, recent_n=recent_n, width=width)


@st.cache_data(show_spinner=False)
def _cached_next_draw_top10(_draws, cache_key, weights_name):
    weights = P2D_WEIGHT_CONFIGS.get(weights_name, P2D_WEIGHT_CONFIGS["WEIGHTS_V1"])
    return generate_next_draw_top10(_draws, weights=weights, min_training_draws=P2D_MIN_TRAIN_DRAWS)


@st.cache_data(show_spinner=False)
def _cached_compare_weight_configs(_draws, cache_key):
    return compare_weight_configs(_draws, min_training_draws=P2D_MIN_TRAIN_DRAWS)


STYLE_RENDERERS = {
    "gold": ("Gold (Asal)", render_base_gold),
    "neon": ("Neon Arcade", render_base_neon),
    "swiss": ("Swiss Editorial", render_base_swiss),
    "casino": ("Emerald Casino", render_base_casino),
    "ticket": ("Retro Ticket", render_base_ticket),
    "soft": ("Soft Neumorphic", render_base_soft),
    "classic": ("Classic Result (Breakcode 4D)", render_base_classic),
}


def render_base_image(style, base, rank_start, rank_end, kombinasi, date_label, result_handle="@Breakcode4d", hot_digits=None, top10_numbers=None, full_date=None, pool_numbers=None):
    if style == "classic":
        # Kad "Classic Result" ada signature sendiri (perlu senarai skor lagi
        # panjang — 23 — drpd Top 10 biasa) — bypass fn() generik.
        return render_base_classic(date_label, result_handle, full_date, pool_numbers)
    _, fn = STYLE_RENDERERS.get(style, STYLE_RENDERERS["gold"])
    return fn(base, rank_start, rank_end, kombinasi, date_label, result_handle, hot_digits, top10_numbers)


# ================================================================== PAGE ===
load_css()

st.markdown(
    """
    <div class="bc4d-header">
        <div class="emoji">🔮</div>
        <div>
            <h1>Breakcode4D — GD Lotto 4D</h1>
            <p>Fokus penuh pada Formula Break &amp; Wheelpick Generator untuk GD4D.</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

draws = load_draws()

if not draws:
    st.warning("⚠️ Tiada data draw lagi. Pergi ke tab **📋 Data Draw** untuk tambah draw dahulu.")
    st.stop()

last_draw = draws[-1]
countdown = str(get_draw_countdown_from_last_8pm()).split(".")[0]

# Amaran jurang tarikh — kesan bila draws.txt nampak belum dikemas kini (andaian
# draw berlaku setiap hari, ikut corak data sedia ada; laraskan kalau tidak).
_today_my = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date()
_last_draw_date = datetime.strptime(last_draw["date"], "%Y-%m-%d").date()
_gap_days = (_today_my - _last_draw_date).days
if _gap_days > 1:
    st.warning(
        f"⚠️ Data draw terakhir direkodkan **{_gap_days} hari lalu** ({last_draw['date']}) — "
        "kemungkinan `draws.txt` belum dikemas kini. Tekan **🔄 Kemas Kini Draw** di tab "
        "Dashboard, atau tambah draw manual di tab **📋 Data Draw**."
    )

st.markdown(
    card_grid([
        card("⏳ Draw Seterusnya", countdown),
        card("📅 Draw Terakhir", last_draw["date"]),
        card("🎯 Keputusan Terakhir", last_draw["number"]),
        card("📊 Jumlah Draw", str(len(draws))),
    ]),
    unsafe_allow_html=True,
)

tab_dash, tab_base, tab_history, tab_wheel, tab_data = st.tabs(
    ["📊 Dashboard", "🔮 Base", "🔎 Semak Nombor", "🎡 Wheelpick", "📋 Data Draw"]
)

# ============================================================= DASHBOARD ===
with tab_dash:
    dash_c1, dash_c2 = st.columns([2.3, 1])
    with dash_c1:
        st.markdown("**📥 Kemas Kini Draw Terkini**")
        st.caption("Tarik keputusan terbaru terus dari sini (perlu sambungan internet).")
    with dash_c2:
        if st.button("🔄 Kemas Kini Draw", key="dash_scrape_btn", use_container_width=True):
            with st.spinner("Menarik keputusan terkini..."):
                msg = scrape_latest()
            st.info(msg)
            st.rerun()

    divider()
    section_title("📌", "Insight Draw Terakhir")

    need_single = DEFAULT_RECENT_N + 1
    need_combined = DEFAULT_RECENT_N + 2

    if len(draws) < need_single:
        st.info(
            f"ℹ️ Perlu sekurang-kurangnya {need_single} draw untuk papar insight "
            f"(ada {len(draws)}). Tambah draw di tab **📋 Data Draw**."
        )
    else:
        base_today_prev = generate_break_base(draws[:-1], recent_n=DEFAULT_RECENT_N)

        st.markdown("**🧮 Base Tunggal (Formula Break)**")
        flags = check_against_base(last_draw["number"], base_today_prev)
        digit_chips(last_draw["number"], flags)

        if len(draws) < need_combined:
            st.info(
                f"ℹ️ Perlu sekurang-kurangnya {need_combined} draw untuk semakan "
                f"Base Gabungan (ada {len(draws)})."
            )
        else:
            base_yesterday_prev = generate_break_base(draws[:-2], recent_n=DEFAULT_RECENT_N)
            combined_prev = combine_bases(base_today_prev, base_yesterday_prev)

            st.markdown("**🔗 Base Gabungan (2 Base)**")
            flags2 = check_against_base(last_draw["number"], combined_prev)
            digit_chips(last_draw["number"], flags2)

        st.markdown(
            '<div class="bc4d-note">Kedua-dua semakan di atas dikira menggunakan draw '
            '<strong>sebelum</strong> keputusan terakhir — supaya adil (tiada maklumat masa depan bocor).</div>',
            unsafe_allow_html=True,
        )

    divider()
    section_title("👍", "Like / Dislike Digit", "Digit paling kerap &amp; paling jarang dalam 30 draw terkini.")
    like, dislike = get_like_dislike_digits(draws)
    st.markdown(
        card_grid(
            [card("👍 Like", " ".join(like) or "—"), card("👎 Dislike", " ".join(dislike) or "—")],
            min_width=140,
        ),
        unsafe_allow_html=True,
    )

    divider()
    section_title(
        "🎯", "TOP 10 RAMALAN 2D — NEXT DRAW",
        "Ranking statistik drpd 9 feature corak sejarah (frequency, recency, position, trend, gap, "
        "cluster, digit, transition, backtest) + walk-forward backtest jujur berbanding baseline rawak. "
        "<strong>Ini BUKAN jaminan keputusan</strong> — GD Lotto ialah draw rawak &amp; bebas; alat ni "
        "cuma ranking statistik sejarah, bukan ramalan pasti.",
    )

    if len(draws) < P2D_MIN_TRAIN_DRAWS + 1:
        st.info(
            f"ℹ️ Perlu sekurang-kurangnya {P2D_MIN_TRAIN_DRAWS + 1} draw utk Top 10 2D + backtest "
            f"(ada {len(draws)}). Tambah draw di tab **📋 Data Draw**."
        )
    else:
        dkey = _draws_cache_key(draws)
        with st.spinner("Mengira walk-forward backtest & Top 10 2D (~10-15 saat kali pertama, selepas tu cache)..."):
            p2d_result = _cached_next_draw_top10(draws, dkey, "WEIGHTS_V1")

        for w in p2d_result.get("data_warnings", []):
            st.warning(f"⚠️ {w}")

        st.caption(
            f"**Last Draw:** {p2d_result['source_last_draw_date']} — {p2d_result['source_last_draw_number']} "
            f"&nbsp;|&nbsp; **Target:** NEXT DRAW &nbsp;|&nbsp; {p2d_result['total_draws_used']} draw digunakan"
        )

        bt = p2d_result["backtest_summary"]
        lift = bt["lift_vs_baseline_pct"]
        st.markdown(
            card_grid([
                card("🧪 Round Diuji", str(bt["draws_tested"])),
                card("🎯 Kadar Hit (Model)", f"{bt['hit_rate_pct']}%"),
                card("🎲 Baseline Rawak", f"{bt['baseline_random_hit_rate_pct']}%"),
                card("📈 Lift vs Baseline", f"{lift:+.2f}%" if lift is not None else "—"),
            ]),
            unsafe_allow_html=True,
        )
        st.markdown(
            card_grid([
                card("📬 Top10 Recall", f"{bt['top10_recall_pct']}%"),
                card("↔️ Avg Rank bila Hit", str(bt["average_prediction_rank_when_hit"] or "—")),
                card("🥇 Best Rank", str(bt["best_rank"] or "—")),
                card("🥉 Worst Rank", str(bt["worst_rank"] or "—")),
            ], min_width=110),
            unsafe_allow_html=True,
        )
        st.caption(
            "**\"Baseline Rawak\"** = kebarangkalian TEPAT (formula probabilistik, bukan simulasi) Top-10 "
            "RAWAK akan sekurang-kurangnya 1 hit, dikira atas round backtest yang SAMA (adil). "
            "**\"Lift\"** hampir 0% (positif atau negatif) bermakna model ni tiada kelebihan sebenar drpd "
            "tekaan rawak — jangkaan yang wajar utk draw yang benar-benar bebas."
        )

        top10_df = pd.DataFrame([
            {
                "Rank": r["rank"],
                "2D": r["number"],
                "Score": round(r["final_score"] * 100, 1),
                "BT Rate": f"{r['backtest_hit_rate'] * 100:.1f}%",
                "BT Samples": r["backtest_predictions"],
                "Gap": r["current_gap"],
            }
            for r in p2d_result["top10"]
        ])
        st.dataframe(top10_df, use_container_width=True, hide_index=True)
        st.code(" ".join(r["number"] for r in p2d_result["top10"]), language="text")

        st.markdown(
            '<div class="bc4d-note">Skor akhir gabungan 9 feature (WEIGHTS_V1) — ranking statistik sejarah '
            'sahaja, <strong>bukan ramalan pasti</strong>. GD Lotto permainan nasib sepenuhnya; '
            'mainlah secara bertanggungjawab &amp; ikut kemampuan sendiri.</div>',
            unsafe_allow_html=True,
        )

        with st.expander("⚙️ Banding Weight Config — WEIGHTS_V1 / V2 / V3 (backtest 3×, lebih lama)"):
            st.caption(
                "Setiap config diuji penuh secara walk-forward, dibahagi validation (separuh awal) vs "
                "test (separuh akhir) — config dipilih guna validation, keputusan akhir dilapor guna test, "
                "supaya pemilihan weight tidak 'curang' atas data yang sama yang dilaporkan."
            )
            if st.button("🔬 Jalankan Perbandingan", key="p2d_compare_btn"):
                with st.spinner("Menjalankan walk-forward backtest utk 3 config (~30-45 saat)..."):
                    comparison = _cached_compare_weight_configs(draws, dkey)
                st.dataframe(pd.DataFrame(comparison["per_config"]).T, use_container_width=True)
                st.caption(f"Dipilih ikut validation: **{comparison['selected_by_validation']}**")

# ===================================================================== BASE ===
with tab_base:
    section_title(
        "🔮", "Base — Formula Break & Kad Kongsi",
        "Satu tempat: tetapkan N &amp; julat rank, dapatkan cadangan, jana base, backtest — "
        "semua guna tarikh &amp; tetapan yang SAMA (tak payah ulang set kat tab lain).",
    )

    if len(draws) < 20:
        st.info(f"ℹ️ Perlu sekurang-kurangnya 20 draw untuk mula (ada {len(draws)}). Tambah draw di tab **📋 Data Draw**.")
    else:
        # ---- 1. Tarikh — SATU sahaja, dikongsi SEMUA bahagian di bawah (grid, kad,
        # cadangan, backtest). Base secara asal disediakan UNTUK draw seterusnya
        # (belum keluar), tapi bagi pilihan tarikh supaya boleh semak/jana balik
        # base bagi mana-mana hari — lepas atau depan.
        today_my = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date()
        last_draw_date = datetime.strptime(last_draw["date"], "%Y-%m-%d").date()
        auto_target_date = max(last_draw_date + timedelta(days=1), today_my)
        first_draw_date = datetime.strptime(draws[0]["date"], "%Y-%m-%d").date()

        dcol1, dcol2 = st.columns([2, 3])
        with dcol1:
            target_date = st.date_input(
                "🗓️ Tarikh Draw",
                value=auto_target_date,
                min_value=first_draw_date,
                max_value=today_my + timedelta(days=7),
                key="base_target_date",
                help="SEMUA bahagian di bawah (base, kad, cadangan, backtest) guna draw "
                     "SEBELUM tarikh ini sahaja — pilih hari lain utk semak balik.",
            )
        with dcol2:
            st.markdown(
                f'<div class="bc4d-note" style="margin-top:28px">📌 Auto (draw seterusnya): '
                f'<strong>{auto_target_date.strftime("%d/%m/%Y")}</strong> &middot; Hari ini: '
                f'<strong>{today_my.strftime("%d/%m/%Y")}</strong></div>',
                unsafe_allow_html=True,
            )

        target_date_str = target_date.strftime("%Y-%m-%d")
        draws_asof = [d for d in draws if d["date"] < target_date_str]
        insufficient_data = len(draws_asof) < 20

        if insufficient_data:
            st.warning(
                f"⚠️ Hanya {len(draws_asof)} draw sebelum {target_date_str} — perlu "
                f"sekurang-kurangnya 20 draw untuk jana apa-apa bagi tarikh ini. Cuba pilih tarikh lain."
            )
        else:
            # ---- 2. Tetapan Base — SATU set, dikongsi SEMUA bahagian di bawah ----
            st.markdown("**⚙️ Tetapan Base**")
            bc1, bc2 = st.columns(2)
            recent_n = bc1.slider(
                "Jumlah draw terkini (N):", 20, len(draws_asof), min(DEFAULT_RECENT_N, len(draws_asof)), 5, key="base_n"
            )
            rank_range = bc2.select_slider(
                "Julat rank digit:", options=list(range(1, 11)), value=DEFAULT_RANK_RANGE, key="base_rank"
            )
            st.caption(
                "💡 Tetapan ni dipakai serentak oleh Base, Kad Kongsi, dan semua tool Analisis di bawah "
                "— satu tempat, tak payah set berulang macam dulu."
            )

            # ---- 3. Cadangan Tetapan Terbaik (N + Julat serentak) ----
            with st.expander("🎯 Cadangan Tetapan Terbaik (N + Julat serentak)"):
                st.caption(
                    "Cari pasangan N + Julat Rank TERBAIK SERENTAK guna backtest SEBENAR (keputusan draw "
                    "yang betul-betul keluar) — bukan satu-satu berasingan, sebab dua tetapan ni saling "
                    "berkait (N terbaik utk satu julat blm tentu terbaik utk julat lain)."
                )
                n_all_options = sorted({
                    n for n in [30, 50, 70, 100, 150, 200, 300, 500, 750, 1000, 1500, 2000, 3000]
                    if n <= len(draws_asof)
                })
                n_default = [n for n in [30, 50, 100, 200, 500] if n in n_all_options] or n_all_options[:5]
                rc1, rc2 = st.columns(2)
                rec_n_candidates = rc1.multiselect(
                    "Saiz N untuk dibandingkan:", options=n_all_options, default=n_default, key="rec_n_candidates",
                )
                rec_rounds_cfg = rc2.slider("Bilangan draw lepas untuk diuji:", 10, 100, 30, 5, key="rec_rounds_cfg")
                rec_combined = st.checkbox("Guna Base Gabungan (bukan tunggal)", key="rec_combined")

                if len(rec_n_candidates) < 1:
                    st.info("Pilih sekurang-kurangnya 1 saiz N untuk dicuba.")
                elif st.button("🚀 Cari Cadangan Terbaik", key="rec_run"):
                    try:
                        with st.spinner("Menguji setiap gabungan N × Julat..."):
                            width = rank_range[1] - rank_range[0] + 1
                            combo_results = recommend_base_config(
                                draws_asof, rec_n_candidates, rounds=rec_rounds_cfg,
                                width=width, combined=rec_combined,
                            )
                        best_combo = combo_results[0]
                        theoretical_baseline = round((width / 10) ** 4 * 100, 3)
                        st.success(
                            f"🏆 **N={best_combo['N (recent_n)']}, Julat {best_combo['Julat']}** paling baik — "
                            f"{best_combo['Match Penuh (4/4)']} match penuh drpd {best_combo['Draw Diuji']} draw "
                            f"diuji (**{best_combo['Hit Rate (%)']}%**), berbanding jangkaan rawak murni "
                            f"{theoretical_baseline}% (lebar julat {width})."
                        )
                        st.dataframe(
                            pd.DataFrame(combo_results).drop(columns=["rank_range"]),
                            use_container_width=True, hide_index=True,
                        )
                        if st.button(
                            f"✅ Guna N={best_combo['N (recent_n)']} + {best_combo['Julat']} Sekarang", key="rec_apply"
                        ):
                            st.session_state["base_n"] = min(best_combo["N (recent_n)"], len(draws_asof))
                            st.session_state["base_rank"] = best_combo["rank_range"]
                            st.rerun()
                        st.caption(
                            "⚠️ Berdasarkan backtest retrospektif sahaja — bukan jaminan keputusan akan datang. "
                            "Julat rank dikekalkan lebar sama (ikut tetapan semasa) semasa carian, supaya adil."
                        )
                    except ValueError as e:
                        st.error(str(e))

            # ---- 4. Base (grid ringkas) ----
            try:
                base = generate_break_base(draws_asof, recent_n=recent_n, rank_range=rank_range)
            except ValueError as e:
                st.error(str(e))
                base = None

            if base:
                rank_start, rank_end = rank_range
                st.markdown("**🔢 Base (boleh salin terus):**")
                st.code("\n".join(" ".join(p) for p in base), language="text")

                actual_draw = next((d for d in draws if d["date"] == target_date_str), None)
                if actual_draw:
                    flags = check_against_base(actual_draw["number"], base)
                    st.success(f"✅ Keputusan sebenar {target_date_str} : **{actual_draw['number']}**")
                    digit_chips(actual_draw["number"], flags)
                else:
                    st.caption(f"ℹ️ Belum ada keputusan direkod untuk {target_date_str} — base ini jana sebagai unjuran.")

                # ---- 5. Kad Kongsi (gambar shareable) ----
                with st.expander("🎴 Jana Kad Kongsi (Gambar)"):
                    style_options = list(STYLE_RENDERERS.keys())
                    card_style = st.selectbox(
                        "🎨 Design kad:", style_options, format_func=lambda k: STYLE_RENDERERS[k][0], key="base_style",
                    )
                    kc1, kc2 = st.columns(2)
                    card_lot = kc1.text_input("Nilai Lot:", value="0.10", key="base_lot")
                    card_score_n = kc2.slider(
                        "Draw untuk kira skor Top 10:",
                        min(10, len(draws_asof)), len(draws_asof), min(DEFAULT_RECENT_N, len(draws_asof)), 5,
                        key="base_score_n",
                    )
                    card_result_handle = st.text_input("Channel/Result handle:", value="@Breakcode4d", key="base_result_handle")
                    hot_digits_input = st.text_input(
                        "✨ Nombor top hari ini (pisah dengan koma):",
                        value="", placeholder="cth: 4,9,2", key="base_hot_digits",
                    )
                    hot_digits = {d.strip() for d in hot_digits_input.split(",") if d.strip().isdigit() and len(d.strip()) == 1}

                    date_label = target_date.strftime("%d/%m")
                    combos = generate_wheel_combos(base, lot=card_lot)
                    top10 = rank_combos(combos, draws_asof, recent_n=card_score_n, top_n=10)
                    top10_numbers = [r["Nombor"] for r in top10]

                    # Kombinasi Utama = pilihan TOP 1 drpd Top 10 (skor kekerapan sebenar
                    # gabungan P1–P4), bukan sekadar cantum digit rank-teratas tiap posisi
                    # secara berasingan — lebih tepat sbb dah kira skor kombinasi sebenar.
                    kombinasi_utama = top10[0]["Nombor"] if top10 else "".join(p[0] for p in base)

                    # Kad "Classic Result" perlukan 23 nombor (bukan 10) supaya Base
                    # Number/Special/Consolation semua SELARI dgn Base hari tersebut —
                    # kira sekali sahaja, hanya bila style ni dipilih.
                    classic_pool_numbers = None
                    if card_style == "classic":
                        top23 = rank_combos(combos, draws_asof, recent_n=card_score_n, top_n=23)
                        classic_pool_numbers = [r["Nombor"] for r in top23]

                    png_bytes = render_base_image(
                        card_style, base, rank_start, rank_end, kombinasi_utama, date_label,
                        card_result_handle, hot_digits, top10_numbers, full_date=target_date,
                        pool_numbers=classic_pool_numbers,
                    )
                    st.image(png_bytes, use_container_width=True)
                    st.download_button(
                        "🖼️ Muat Turun Gambar Base (PNG)",
                        data=png_bytes,
                        file_name=f"base_{card_style}_{date_label.replace('/', '-')}.png",
                        mime="image/png",
                        key="dl_base_png",
                    )
                    st.caption("Tekan lama / klik kanan gambar di atas untuk terus simpan atau screenshot.")

                    st.markdown(gold_top10_card(top10), unsafe_allow_html=True)

                    top10_line = ", ".join(top10_numbers)
                    share_text = (
                        f"🔮 {date_label} Breakcode Base Draw!!!!\n"
                        f"🕹 Belian bebas ikut anda ibox/tegak dimana\u00b2 rumah (Recommended GD Lotto)\n\n"
                        f"Result : {card_result_handle}\n"
                        f"-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+\n\n"
                        f"🏆 Kombinasi Utama : {kombinasi_utama}\n\n"
                        f"-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+\n"
                        f"🎯 Top 10 Set\n"
                        f"{top10_line}\n"
                        f"-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+"
                    )

                    divider()
                    st.markdown("**📋 Teks Salin (untuk Telegram)** — guna ikon salin di kad di bawah:")
                    st.code(share_text, language="text")
                    st.download_button(
                        "💾 Muat Turun Teks (.txt)",
                        data=share_text.encode(),
                        file_name=f"base_{date_label.replace('/', '-')}.txt",
                        mime="text/plain",
                        key="dl_base_card",
                    )
            else:
                st.info("ℹ️ Tidak dapat jana base dengan tetapan semasa.")

            # ---- 6. Analisis Lanjutan (Backtest, Chi-Square, Ensemble) ----
            with st.expander("🔬 Analisis Lanjutan — Backtest, Chi-Square, Ensemble"):
                st.caption(
                    "Tool utk faham sejauh mana Formula Break ni benar-benar ada *edge* berbanding rawak, "
                    "guna N &amp; Julat rank yang sama macam tetapan di atas."
                )

                st.markdown("**🔁 Backtest — uji prestasi sebenar**")
                bt_mode = st.radio(
                    "Kaedah:", ["Base Tunggal", "Base Gabungan (2 Base)"], horizontal=True, key="bt_mode"
                )
                bt_rounds = st.slider("Bilangan draw lepas untuk diuji:", 5, 50, 10, 5, key="bt_rounds")
                if st.button("🚀 Jalankan Backtest", key="bt_run"):
                    is_combined = bt_mode != "Base Tunggal"
                    if not is_combined:
                        bt_records, bt_full, bt_rate = backtest_break(draws_asof, recent_n, bt_rounds, rank_range)
                    else:
                        bt_records, bt_full, bt_rate = backtest_combined(draws_asof, recent_n, bt_rounds, rank_range)
                    if bt_records:
                        bt_baseline = backtest_random_baseline(draws_asof, recent_n, bt_rounds, rank_range, is_combined)
                        bcol1, bcol2 = st.columns(2)
                        with bcol1:
                            st.success(f"🧮 Formula Break: {bt_full} / {len(bt_records)} draw → **{bt_rate}%**")
                        with bcol2:
                            st.info(
                                f"🎲 Baseline Rawak (jangkaan): {bt_baseline['expected_full_match']} / "
                                f"{bt_baseline['evaluated']} draw → **{bt_baseline['baseline_rate']}%**"
                            )
                        if bt_rate > bt_baseline["baseline_rate"]:
                            st.caption("✅ Formula Break mengatasi jangkaan rawak murni — petunjuk mungkin ada corak (bukan bukti muktamad).")
                        else:
                            st.caption("⚠️ TIDAK mengatasi (atau setara sahaja dgn) jangkaan rawak murni — anggap keputusan sbg sekadar nasib buat masa ini.")
                        st.dataframe(pd.DataFrame(bt_records), use_container_width=True, hide_index=True)
                    else:
                        st.warning("Data tidak mencukupi untuk backtest dengan tetapan ini.")

                divider()
                st.markdown("**🔍 Cari N Terbaik (julat rank dikekalkan ikut tetapan atas)**")
                n_all_options2 = sorted({
                    n for n in [30, 50, 70, 100, 150, 200, 300, 500, 750, 1000, 1500, 2000, 3000]
                    if n <= len(draws_asof)
                })
                n_default2 = [n for n in [30, 50, 100, 200, 500] if n in n_all_options2] or n_all_options2[:5]
                n_candidates_sel = st.multiselect(
                    "Saiz N untuk dibandingkan:", options=n_all_options2, default=n_default2, key="n_search_candidates",
                )
                ncol1, ncol2 = st.columns(2)
                n_search_rounds = ncol1.slider("Bilangan draw lepas untuk diuji:", 10, 100, 30, 5, key="n_search_rounds")
                n_search_combined = ncol2.checkbox("Guna Base Gabungan (bukan tunggal)", key="n_search_combined")

                if len(n_candidates_sel) < 2:
                    st.info("Pilih sekurang-kurangnya 2 saiz N untuk perbandingan.")
                elif st.button("🚀 Cari N Terbaik", key="n_search_run"):
                    try:
                        with st.spinner("Menguji setiap saiz N..."):
                            n_results = recommend_recent_n(
                                draws_asof, n_candidates_sel, rounds=n_search_rounds,
                                rank_range=rank_range, combined=n_search_combined,
                            )
                        best_n = n_results[0]
                        st.success(
                            f"🏆 **N={best_n['N (recent_n)']}** paling baik — {best_n['Match Penuh (4/4)']} match "
                            f"penuh drpd {best_n['Draw Diuji']} draw diuji (**{best_n['Hit Rate (%)']}%**)."
                        )
                        st.dataframe(pd.DataFrame(n_results), use_container_width=True, hide_index=True)
                        if st.button(f"✅ Guna N={best_n['N (recent_n)']} Sekarang", key="n_search_apply"):
                            st.session_state["base_n"] = min(best_n["N (recent_n)"], len(draws_asof))
                            st.rerun()
                    except ValueError as e:
                        st.error(str(e))

                divider()
                st.markdown("**📐 Ujian Statistik — Chi-Square (taburan digit)**")
                st.caption(
                    "p < 0.05 = mungkin ada corak; p ≥ 0.05 = taburan digit nampak macam rawak untuk N draw ini."
                )
                try:
                    chi_results = chi_square_uniformity(draws_asof, recent_n=recent_n)
                    st.dataframe(pd.DataFrame(chi_results), use_container_width=True, hide_index=True)
                    n_sig = sum(1 for r in chi_results if r["Signifikan (p<0.05)"].startswith("Ya"))
                    if n_sig == 0:
                        st.caption("⚠️ Tiada posisi menunjukkan penyimpangan signifikan drpd rawak.")
                    else:
                        st.caption(f"ℹ️ {n_sig} drpd 4 posisi menunjukkan penyimpangan signifikan (p<0.05).")
                except ValueError as e:
                    st.error(str(e))

                divider()
                st.markdown("**🧬 Ensemble — Digit Stabil Merentasi Beberapa N**")
                ens_options = sorted({n for n in [20, 30, 50, 100, 150, 200] if n <= len(draws_asof)})
                chosen_n = st.multiselect(
                    "Saiz N untuk dibandingkan:", options=ens_options,
                    default=[n for n in [30, 50, 100] if n in ens_options], key="ens_n_values",
                )
                if len(chosen_n) < 2:
                    st.info("Pilih sekurang-kurangnya 2 saiz N untuk perbandingan.")
                else:
                    try:
                        ens_results = ensemble_stable_digits(draws_asof, n_values=chosen_n, rank_range=rank_range)
                        st.dataframe(pd.DataFrame(ens_results), use_container_width=True, hide_index=True)

                        ens_base = [
                            row["Digit Stabil (semua N)"].split(", ") if row["Digit Stabil (semua N)"] != "—" else []
                            for row in ens_results
                        ]
                        empty_positions = [row["Posisi"] for row, digits in zip(ens_results, ens_base) if not digits]
                        if empty_positions:
                            st.warning(
                                f"⚠️ Posisi {', '.join(empty_positions)} tiada digit stabil merentasi SEMUA N yang "
                                "dipilih — base ni tak lengkap, tak boleh digunakan terus dalam Wheelpick. Cuba "
                                "kurangkan bilangan N dipilih, atau kelonggarkan julat rank di atas."
                            )
                        else:
                            st.markdown("**🔢 Base Ensemble (Digit Stabil Semua N) — boleh salin terus:**")
                            st.code("\n".join(" ".join(p) for p in ens_base), language="text")
                    except ValueError as e:
                        st.error(str(e))

# =================================================================== HISTORY ===
with tab_history:
    section_title(
        "🔎", "Semak Nombor — Sejarah &amp; Cadangan Julat",
        "Beza dgn tab <strong>🔮 Base</strong> (cadangan julat SECARA UMUM): kat sini awak masukkan "
        "SATU nombor sasaran (P1–P4) yg awak dah ada dlm fikiran, dan semak bila/sejauh mana nombor "
        "tu pernah muncul dlm base sepanjang sejarah.",
    )

    if len(draws) < 20:
        st.warning("⚠️ Data draw terlalu sedikit (<20). Tambah draw di tab **📋 Data Draw** dahulu.")
    else:
        target_input = st.text_input(
            "🔢 Nombor Sasaran (P1 P2 P3 P4):", value="", placeholder="cth: 1 2 3 4", key="hist_target"
        )
        target_digits = target_input.strip().split()

        hc1, hc2 = st.columns(2)
        hist_recent_n = hc1.slider(
            "Jumlah draw terkini (per tarikh):", 20, len(draws), min(DEFAULT_RECENT_N, len(draws)), 5, key="hist_n"
        )
        hist_rank_range = hc2.select_slider(
            "Julat rank digit:", options=list(range(1, 11)), value=DEFAULT_RANK_RANGE, key="hist_rank"
        )
        min_match = st.select_slider(
            "Papar tarikh dengan sekurang-kurangnya:",
            options=[1, 2, 3, 4], value=1,
            format_func=lambda v: f"{v} padanan", key="hist_min_match",
        )

        if not target_input.strip():
            st.caption("ℹ️ Masukkan 4 digit sasaran (satu bagi setiap P1–P4) untuk mula semak — cth: 1 2 3 4")
        elif len(target_digits) != 4 or not all(len(t) == 1 and t.isdigit() for t in target_digits):
            st.error("❌ Format tidak sah — masukkan tepat 4 digit tunggal, dipisah space (cth: 1 2 3 4).")
        else:
            dkey = _draws_cache_key(draws)
            try:
                records = _cached_scan_digit_history(
                    draws, dkey, target_digits, hist_recent_n, hist_rank_range, min_match
                )
            except ValueError as e:
                st.error(str(e))
                records = []

            st.markdown(f"**📜 Senarai Tarikh Sepadan** ({len(records)} tarikh ditemui):")
            if records:
                st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)
            else:
                st.info("Tiada tarikh sepadan dengan tetapan semasa. Cuba turunkan minimum padanan atau ubah julat rank.")

            rank_start, rank_end = hist_rank_range
            width = rank_end - rank_start + 1
            try:
                recs = _cached_recommend_rank_range(draws, dkey, target_digits, hist_recent_n, width)
            except ValueError as e:
                recs = []
                st.error(str(e))

            if recs:
                best = recs[0]
                best_evaluated = best["Draw Diuji"]
                best_rate = round(best["Match Penuh (4/4)"] / best_evaluated * 100, 2) if best_evaluated else 0.0
                theoretical_baseline = round((width / 10) ** 4 * 100, 3)
                current_entry = next((r for r in recs if r["rank_range"] == tuple(hist_rank_range)), None)

                next_draw_date = max(_last_draw_date + timedelta(days=1), _today_my)

                st.markdown(
                    f"**🎯 Ramalan & Cadangan Base — Draw Akan Datang ({next_draw_date.strftime('%d/%m/%Y')})**"
                )
                st.success(
                    f"Untuk nombor sasaran **{''.join(target_digits)}**, base yang dicadangkan: **{best['Julat']}**"
                )

                reasons = [
                    f"🎯 **{best['Match Penuh (4/4)']} match penuh (4/4)** drpd {best_evaluated} draw diuji "
                    f"sepanjang sejarah (**{best_rate}%**) — PALING TINGGI antara semua julat lebar {width} yang dicuba."
                ]
                if best_rate > theoretical_baseline:
                    mult = round(best_rate / theoretical_baseline, 1) if theoretical_baseline else None
                    reasons.append(
                        f"📊 Ini **{mult}× ganda** lebih tinggi drpd jangkaan rawak murni ({theoretical_baseline}% "
                        f"untuk lebar julat {width}) — petunjuk mungkin ada corak, bukan sekadar nasib."
                    )
                else:
                    reasons.append(
                        f"⚠️ Kadar ini ({best_rate}%) hampir sama / lebih rendah drpd jangkaan rawak murni "
                        f"({theoretical_baseline}%) — anggap cadangan ni sbg panduan sahaja, bukan bukti corak sebenar."
                    )
                if current_entry and current_entry["Julat"] != best["Julat"]:
                    diff = best["Match Penuh (4/4)"] - current_entry["Match Penuh (4/4)"]
                    reasons.append(
                        f"🔁 Berbanding tetapan semasa anda (**{current_entry['Julat']}**, "
                        f"{current_entry['Match Penuh (4/4)']} match penuh), julat dicadangkan ada "
                        f"**{diff:+d} match penuh**."
                    )
                elif current_entry:
                    reasons.append(f"✅ Ini SAMA dengan tetapan semasa anda (**{current_entry['Julat']}**) — tak perlu tukar.")

                for r in reasons:
                    st.markdown(f"- {r}")

                try:
                    recommended_base = generate_break_base(draws, recent_n=hist_recent_n, rank_range=best["rank_range"])
                    st.markdown("**🔢 Base sebenar (julat dicadangkan, data terkini — boleh terus pakai):**")
                    st.code("\n".join(" ".join(p) for p in recommended_base), language="text")
                except ValueError as e:
                    st.error(str(e))

                st.caption(
                    "⚠️ Cadangan ni berdasarkan corak sejarah sahaja (backtest retrospektif) — bukan jaminan "
                    "keputusan sebenar. Sila guna sebagai panduan, bukan kepastian."
                )

                with st.expander("Lihat perbandingan semua julat (lebar sama)"):
                    cmp_df = pd.DataFrame(recs)[["Julat", "Jumlah Padanan Digit", "Match Penuh (4/4)", "Draw Diuji"]]
                    st.dataframe(cmp_df, use_container_width=True, hide_index=True)

# ================================================================ WHEELPICK ===
with tab_wheel:
    section_title("🎡", "Wheelpick Generator")

    arah_wp = st.radio("Arah susunan:", ["Kiri→Kanan", "Kanan→Kiri"], horizontal=True, key="wp_dir")

    like, dislike = get_like_dislike_digits(draws)
    user_like = st.text_input("Digit Like:", value=" ".join(like), key="wp_like")
    user_dislike = st.text_input("Digit Dislike:", value=" ".join(dislike), key="wp_dislike")
    likes, dislikes = user_like.split(), user_dislike.split()

    input_mode = st.radio(
        "Sumber Base:",
        ["Auto — Formula Break", "Gabung 2 Base (Hari ini + Semalam)", "Manual", "Gabung 2 Base (Manual)"],
        key="wp_mode",
    )

    base_wp = None
    if input_mode == "Auto — Formula Break":
        if len(draws) < 20:
            st.warning("⚠️ Data draw terlalu sedikit (<20) untuk jana base secara automatik.")
        else:
            recent_wp = st.slider(
                "Jumlah draw untuk base:", 20, len(draws), min(DEFAULT_RECENT_N, len(draws)), 5, key="wp_n"
            )
            try:
                base_wp = generate_break_base(draws, recent_n=recent_wp)
                st.code("\n".join(" ".join(p) for p in base_wp), language="text")
            except ValueError as e:
                st.error(str(e))
    elif input_mode == "Gabung 2 Base (Hari ini + Semalam)":
        if len(draws) < 21:
            st.warning("⚠️ Data draw terlalu sedikit (<21) untuk jana base hari ini & semalam.")
        else:
            recent_combo = st.slider(
                "Jumlah draw untuk base:",
                20, len(draws) - 1, min(DEFAULT_RECENT_N, len(draws) - 1), 5, key="wp_combo_n",
            )
            try:
                base_today = generate_break_base(draws, recent_n=recent_combo)
                base_yesterday = generate_break_base(draws[:-1], recent_n=recent_combo)
                base_wp = combine_bases(base_today, base_yesterday)

                st.markdown("**📅 Base Hari Ini:**")
                st.code("\n".join(" ".join(p) for p in base_today), language="text")
                st.markdown("**📆 Base Semalam:**")
                st.code("\n".join(" ".join(p) for p in base_yesterday), language="text")
                st.markdown("**🔗 Base Gabungan (dipakai untuk Wheelpick):**")
                st.code("\n".join(" ".join(p) for p in base_wp), language="text")
            except ValueError as e:
                st.error(str(e))
    elif input_mode == "Manual":
        manual_base = st.text_area(
            "Masukkan Base Manual (4 baris, digit dipisah space):", height=120, key="wp_manual"
        )
        lines = [ln.strip().split() for ln in manual_base.strip().split("\n") if ln.strip()]
        if manual_base.strip() and len(lines) == 4 and all(lines):
            base_wp = lines
        elif manual_base.strip():
            st.error("❌ Format base tidak sah — perlu tepat 4 baris, setiap baris ada sekurang-kurangnya satu digit.")
    else:
        st.caption("Taip/tampal 2 base (cth: satu drpd channel lain, satu lagi base sendiri) — akan digabungkan sama macam mod \"Gabung 2 Base (Hari ini + Semalam)\", tapi kedua-dua base ditaip sendiri.")
        mc1, mc2 = st.columns(2)
        with mc1:
            st.markdown("**📋 Base Manual 1:**")
            manual_base_1 = st.text_area(
                "4 baris, digit dipisah space:", height=120, key="wp_manual_1"
            )
        with mc2:
            st.markdown("**📋 Base Manual 2:**")
            manual_base_2 = st.text_area(
                "4 baris, digit dipisah space:", height=120, key="wp_manual_2"
            )

        def _parse_manual_base(raw: str):
            ln = [x.strip().split() for x in raw.strip().split("\n") if x.strip()]
            if raw.strip() and len(ln) == 4 and all(ln):
                return ln
            return None

        parsed_1 = _parse_manual_base(manual_base_1)
        parsed_2 = _parse_manual_base(manual_base_2)

        if manual_base_1.strip() and not parsed_1:
            st.error("❌ Format Base 1 tidak sah — perlu tepat 4 baris, setiap baris ada sekurang-kurangnya satu digit.")
        if manual_base_2.strip() and not parsed_2:
            st.error("❌ Format Base 2 tidak sah — perlu tepat 4 baris, setiap baris ada sekurang-kurangnya satu digit.")

        if parsed_1 and parsed_2:
            try:
                base_wp = combine_bases(parsed_1, parsed_2)
                st.markdown("**🔗 Base Gabungan (dipakai untuk Wheelpick):**")
                st.code("\n".join(" ".join(p) for p in base_wp), language="text")
            except ValueError as e:
                st.error(str(e))

    if base_wp:
        lot = st.text_input("Nilai Lot:", value="0.10", key="wp_lot")
        score_n = st.slider(
            "Jumlah draw untuk kira skor Top 10:",
            min(10, len(draws)), len(draws), min(DEFAULT_RECENT_N, len(draws)), 5, key="wp_score_n",
        )

        with st.expander("⚙️ Tapisan Tambahan"):
            fc1, fc2, fc3 = st.columns(3)
            no_repeat = fc1.checkbox("Buang digit ulang", key="f1")
            no_triple = fc1.checkbox("Buang triple", key="f2")
            no_pair = fc2.checkbox("Buang pair", key="f3")
            no_ascend = fc2.checkbox("Buang menaik", key="f4")
            use_history = fc3.checkbox("Buang pernah keluar", key="f5")
            sim_limit = st.slider("Max sama posisi dgn draw terakhir:", 0, 4, 2, key="f6")

        with st.expander("🎯 Filter 2D/1D (Tikam Nombor)"):
            st.caption(
                "Beza dgn **Digit Like/Dislike** di atas (semak SATU digit sahaja): di sini boleh "
                "masukkan nombor **2D** (cth `36`) — kombinasi 4D mesti ada **KEDUA-DUA** digit 3 "
                "DAN 6 sekali (bukan cuma salah satu) utk dikira padan. Mod **1D** pula sama macam "
                "biasa (satu digit sahaja tiap entri)."
            )
            f2d_mode = st.radio("Mod:", ["1D", "2D"], horizontal=True, key="wp_2d_mode")
            digit_len = 1 if f2d_mode == "1D" else 2
            contoh = "3 5 8" if digit_len == 1 else "36 58 92"

            f2d_like_raw = st.text_input(
                f"Like ({f2d_mode}) — nombor dipisah space, cth {contoh}:", key="wp_2d_like"
            )
            f2d_dislike_raw = st.text_input(
                f"Dislike ({f2d_mode}) — nombor dipisah space:", key="wp_2d_dislike"
            )

            def _parse_2d1d(raw: str, dlen: int) -> tuple[list[str], list[str]]:
                toks = raw.split()
                valid = [t for t in toks if len(t) == dlen and t.isdigit()]
                invalid = [t for t in toks if t not in valid]
                return valid, invalid

            likes_2d, invalid_like_2d = _parse_2d1d(f2d_like_raw, digit_len)
            dislikes_2d, invalid_dislike_2d = _parse_2d1d(f2d_dislike_raw, digit_len)

            if invalid_like_2d:
                st.error(f"❌ Abaikan (bukan {digit_len} digit sah): {', '.join(invalid_like_2d)}")
            if invalid_dislike_2d:
                st.error(f"❌ Abaikan (bukan {digit_len} digit sah): {', '.join(invalid_dislike_2d)}")
            if likes_2d:
                st.caption(f"✅ Like {f2d_mode} aktif: {', '.join(likes_2d)}")
            if dislikes_2d:
                st.caption(f"🚫 Dislike {f2d_mode} aktif: {', '.join(dislikes_2d)}")

        if st.button("🎰 Jana Wheelpick", key="wp_run"):
            arah = "kiri" if arah_wp == "Kiri→Kanan" else "kanan"
            combos = generate_wheel_combos(base_wp, lot=lot, arah=arah)
            filtered = filter_wheel_combos(
                combos, draws, no_repeat, no_triple, no_pair, no_ascend, use_history, sim_limit, likes, dislikes
            )
            filtered = filter_by_2d1d(filtered, likes_2d, dislikes_2d)
            st.session_state["wp_combos_n"] = len(combos)
            st.session_state["wp_filtered"] = filtered

        if "wp_filtered" in st.session_state:
            filtered = st.session_state["wp_filtered"]
            st.info(f"Sebelum tapis: **{st.session_state['wp_combos_n']}** kombinasi")
            st.success(f"✅ Selepas tapis: **{len(filtered)}** kombinasi")

            plain_filtered = [c.split("#####")[0] for c in filtered]
            st.markdown("**📋 Senarai Kombinasi (selepas tapis):**")
            st.code(", ".join(plain_filtered), language="text")

            if filtered:
                st.download_button(
                    "💾 Muat Turun Wheelpick",
                    data="\n".join(filtered).encode(),
                    file_name="wheelpick.txt",
                    mime="text/plain",
                )

                divider()
                style_options = {
                    "Sum (Asal — kekerapan digit)": "sum",
                    "Geometric Mean (semua posisi kena \"okay\")": "geometric",
                    "Voting (bilangan posisi top-3)": "voting",
                    "Overdue (digit lama tak keluar)": "overdue",
                }
                style_label = st.selectbox(
                    "Gaya skor Top-N:", list(style_options.keys()), index=0, key="wp_style",
                )
                score_style = style_options[style_label]

                top_n_choice = st.selectbox(
                    "Pilih jumlah TOP:", [10, 20, 30, 50, 100, 150, 200],
                    index=0, key="wp_top_n",
                )
                section_title(
                    "🏆", f"Top {top_n_choice} Pilihan",
                    f"Disusun ikut gaya \"{style_label}\" — {score_n} draw terkini.",
                )
                if score_style == "sum":
                    top_results = rank_combos(filtered, draws, recent_n=score_n, top_n=top_n_choice)
                else:
                    scored_all = score_combos_by_style(filtered, draws, recent_n=score_n, style=score_style)
                    top_results = [{"Rank": i + 1, **r} for i, r in enumerate(scored_all[:top_n_choice])]
                st.dataframe(pd.DataFrame(top_results), use_container_width=True, hide_index=True)

                chunk_size = 10
                sets = [top_results[i : i + chunk_size] for i in range(0, len(top_results), chunk_size)]
                set_lines = []
                for idx, s in enumerate(sets, start=1):
                    set_lines.append(f"Set {idx}")
                    set_lines.append(", ".join(r["Nombor"] for r in s))
                sets_text = "\n".join(set_lines)

                st.markdown(f"**📋 Ikut Set (10 nombor/set — {len(sets)} set):**")
                st.code(sets_text, language="text")
                st.download_button(
                    "💾 Muat Turun Set",
                    data=sets_text.encode(),
                    file_name=f"wheelpick_top{top_n_choice}_sets.txt",
                    mime="text/plain",
                    key="dl_top_sets",
                )

                top_results_text = "\n".join(f"{r['Nombor']}#####{r['Lot']}" for r in top_results)
                st.download_button(
                    f"💾 Muat Turun Top {top_n_choice} (format lot)",
                    data=top_results_text.encode(),
                    file_name=f"wheelpick_top{top_n_choice}.txt",
                    mime="text/plain",
                    key="dl_top10",
                )

                divider()
                with st.expander("🔬 Backtest Top-N — adakah skor ni memang ada *edge*?"):
                    st.caption(
                        "Uji Top-N ni terhadap draw LEPAS (base + kombinasi dijana semula setiap kali, "
                        "\"as of\" — tiada bocor maklumat masa depan). Bagi setiap draw yang base-nya "
                        "match penuh, semak sama ada nombor sebenar tersenarai dalam Top-N, lalu banding "
                        "dengan baseline rawak tulen (Top-N ÷ saiz kolam)."
                    )
                    wbc1, wbc2, wbc3 = st.columns(3)
                    wbt_base_n = wbc1.slider(
                        "N base untuk diuji:", 20, len(draws), min(500, len(draws)), 10, key="wbt_base_n",
                    )
                    wbt_rank_range = wbc2.select_slider(
                        "Julat rank digit:", options=list(range(1, 11)), value=DEFAULT_RANK_RANGE, key="wbt_rank_range",
                    )
                    wbt_top_n = wbc3.selectbox(
                        "Top-N untuk diuji:", [10, 20, 30, 50, 100, 150, 200],
                        index=[10, 20, 30, 50, 100, 150, 200].index(top_n_choice)
                        if top_n_choice in [10, 20, 30, 50, 100, 150, 200] else 4,
                        key="wbt_top_n",
                    )
                    wbc4, wbc5 = st.columns(2)
                    wbt_style_label = wbc4.selectbox(
                        "Gaya skor untuk diuji:", list(style_options.keys()), index=0, key="wbt_style",
                    )
                    wbt_style = style_options[wbt_style_label]
                    wbt_rounds = wbc5.slider(
                        "Bilangan draw lepas untuk diuji:", 20, min(500, len(draws)), 200, 10, key="wbt_rounds",
                    )
                    if st.button("🚀 Jalankan Backtest Top-N", key="wbt_run"):
                        with st.spinner("Menguji draw lepas satu-satu..."):
                            wbt_records, wbt_summary = backtest_wheelpick_topn(
                                draws,
                                base_recent_n=wbt_base_n,
                                rank_range=wbt_rank_range,
                                score_recent_n=score_n,
                                top_n=wbt_top_n,
                                rounds=wbt_rounds,
                                style=wbt_style,
                                no_repeat=no_repeat, no_triple=no_triple, no_pair=no_pair,
                                no_ascend=no_ascend, use_history=use_history, sim_limit=sim_limit,
                                likes=likes, dislikes=dislikes, likes_2d=likes_2d, dislikes_2d=dislikes_2d,
                            )
                        if wbt_summary["base_penuh"] == 0:
                            st.warning("⚠️ Tiada draw dalam julat diuji yang base-nya match penuh — cuba tambah bilangan draw diuji.")
                        else:
                            wcol1, wcol2 = st.columns(2)
                            with wcol1:
                                st.success(
                                    f"🧮 Recall Top-{wbt_top_n} sebenar: {wbt_summary['masuk_top_n']} / "
                                    f"{wbt_summary['base_penuh']} draw (base penuh) → **{wbt_summary['recall_rate']}%**"
                                )
                            with wcol2:
                                st.info(f"🎲 Baseline rawak tulen: **{wbt_summary['baseline_rawak']}%**")
                            if wbt_summary["kelebihan_vs_rawak"] > 0:
                                st.caption(f"✅ Mengatasi baseline rawak sebanyak {wbt_summary['kelebihan_vs_rawak']} mata peratusan — petunjuk mungkin ada corak (bukan bukti muktamad).")
                            else:
                                st.caption(f"⚠️ TIDAK mengatasi (atau setara/lebih rendah drpd) baseline rawak ({wbt_summary['kelebihan_vs_rawak']} mata peratusan) — anggap Top-N ni sekadar nasib buat masa ini, bukan formula skor yang \"lebih pandai\".")
                            st.dataframe(pd.DataFrame(wbt_records), use_container_width=True, hide_index=True)

                            passed_nums = [
                                r["Nombor"] for r in wbt_records
                                if r[f"Masuk Top {wbt_top_n}"] == "✅"
                            ]
                            divider()
                            if passed_nums:
                                st.markdown(
                                    f"**📋 Nombor Lulus Backtest (pernah masuk Top {wbt_top_n}) — {len(passed_nums)} nombor:**"
                                )
                                passed_text = "\n".join(f"{n}#####{lot}" for n in passed_nums)
                                st.code(", ".join(passed_nums), language="text")
                                st.download_button(
                                    f"💾 Muat Turun Nombor Lulus (format lot)",
                                    data=passed_text.encode(),
                                    file_name=f"wheelpick_backtest_lulus_top{wbt_top_n}.txt",
                                    mime="text/plain",
                                    key="dl_backtest_lulus",
                                )
                            else:
                                st.caption(f"ℹ️ Tiada nombor yang lulus (masuk Top {wbt_top_n}) dalam julat draw yang diuji.")

                    divider()
                    st.markdown("**⚖️ Banding SEMUA gaya skor sekali gus (N base, julat & Top-N sama):**")
                    if st.button("📊 Banding Semua Gaya Skor", key="wbt_compare_run"):
                        with st.spinner("Menguji 4 gaya skor terhadap draw lepas..."):
                            try:
                                cmp_results = compare_scoring_styles(
                                    draws,
                                    base_recent_n=wbt_base_n,
                                    rank_range=wbt_rank_range,
                                    score_recent_n=score_n,
                                    top_n=wbt_top_n,
                                    rounds=wbt_rounds,
                                    no_repeat=no_repeat, no_triple=no_triple, no_pair=no_pair,
                                    no_ascend=no_ascend, use_history=use_history, sim_limit=sim_limit,
                                    likes=likes, dislikes=dislikes, likes_2d=likes_2d, dislikes_2d=dislikes_2d,
                                )
                            except ValueError as e:
                                st.warning(f"⚠️ {e}")
                            else:
                                sample_n = cmp_results[0]["Base Penuh"]
                                if sample_n < 30:
                                    st.caption(
                                        f"⚠️ Cuma {sample_n} sampel (base penuh) — naikkan \"Bilangan draw lepas untuk diuji\" "
                                        "untuk keputusan yang lebih boleh dipercayai sebelum buat kesimpulan."
                                    )
                                st.dataframe(pd.DataFrame(cmp_results), use_container_width=True, hide_index=True)
                                winner = cmp_results[0]
                                if winner["Kelebihan vs Rawak"] > 0:
                                    st.caption(
                                        f"🏆 \"{winner['Gaya Skor']}\" terdepan (+{winner['Kelebihan vs Rawak']} drpd rawak) — "
                                        "tapi anggap ni petunjuk awal, bukan bukti muktamad, terutama kalau sampel masih kecil."
                                    )
                                else:
                                    st.caption("⚠️ Tiada satu gaya skor pun mengatasi baseline rawak dalam ujian ini.")
            else:
                st.info("ℹ️ Tiada kombinasi selepas tapis untuk jana Top 10.")
    else:
        st.info("ℹ️ Sediakan base (auto atau manual) di atas untuk jana Wheelpick.")

# ================================================================ DATA DRAW ===
with tab_data:
    section_title("📋", "Data Draw", "Sumber data mentah untuk Formula Break &amp; Wheelpick.")

    d1, d2 = st.columns(2)
    with d1:
        st.markdown("**➕ Tambah Draw Manual**")
        new_date = st.text_input("Tarikh (YYYY-MM-DD):", key="add_date")
        new_number = st.text_input("Nombor (4 digit):", key="add_number")
        if st.button("Tambah", key="add_btn"):
            ok, msg = add_draw(new_date, new_number)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    with d2:
        st.markdown("**📥 Kemas Kini Automatik**")
        st.caption("Cuba tarik keputusan terkini secara automatik (perlu sambungan internet).")
        if st.button("Kemas Kini Draw", key="scrape_btn"):
            msg = scrape_latest()
            st.info(msg)
            st.rerun()

    divider()
    col_list, col_dl = st.columns([3, 1])
    col_list.markdown(f"**📜 Senarai Draw** (jumlah: {len(draws)})")
    draws_txt_path = Path(DRAW_FILE)
    if draws_txt_path.exists():
        col_dl.download_button(
            "💾 draws.txt",
            data=draws_txt_path.read_bytes(),
            file_name="draws.txt",
            mime="text/plain",
            key="dl_draws_txt",
        )
    df_draws = pd.DataFrame(draws[::-1])
    st.dataframe(df_draws, use_container_width=True, height=420, hide_index=True)
