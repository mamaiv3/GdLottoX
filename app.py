"""
app.py — Breakcode4D (versi ringkas)
--------------------------------------
Fokus penuh pada:
  1. Formula Break  — jana & uji base P1–P4
  2. Wheelpick      — jana & tapis kombinasi 4D
  3. Data Draw      — data sokongan (sejarah keputusan)
"""

import io
from datetime import datetime
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
    check_against_base,
    combine_bases,
    generate_break_base,
)
from core.wheelpick import filter_wheel_combos, generate_wheel_combos, get_like_dislike_digits, rank_combos

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


def render_base_image(
    base: list[list[str]],
    rank_start: int,
    rank_end: int,
    kombinasi: str,
    date_label: str,
    result_handle: str = "@Breakcode4d",
) -> bytes:
    """Lukis kad 'Base Draw' (gold/black) sebagai PNG sebenar — boleh muat turun atau screenshot terus."""
    W, H = 1000, 1300
    GOLD = (212, 175, 55)
    GOLD_LT = (244, 226, 161)
    BG = (8, 6, 3)
    CREAM = (231, 220, 184)
    MUTED = (138, 124, 80)
    DARK_TXT = (18, 14, 6)
    SILVER = (210, 212, 222)
    BRONZE = (198, 149, 94)

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
    tiers = {0: GOLD_LT, 1: SILVER, 2: BRONZE}
    for row_i in range(n_rows):
        rank_no = rank_start + row_i
        tier_bg = tiers.get(row_i)
        row_box = (table_x0, row_y, table_x1, row_y + row_h)
        if tier_bg:
            draw.rectangle(row_box, fill=tier_bg)
        rank_col = DARK_TXT if tier_bg else MUTED
        _center_text(draw, table_x0 + lbl_w / 2, row_y + row_h / 2 + 2, f"R{rank_no}", f_rank, rank_col)
        for i, p in enumerate(base):
            digit = p[row_i] if row_i < len(p) else "\u2014"
            cx = table_x0 + lbl_w + col_w * i + col_w / 2
            col = DARK_TXT if tier_bg else CREAM
            _center_text(draw, cx, row_y + row_h / 2 + 2, digit, f_cell, col)
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

st.markdown(
    card_grid([
        card("⏳ Draw Seterusnya", countdown),
        card("📅 Draw Terakhir", last_draw["date"]),
        card("🎯 Keputusan Terakhir", last_draw["number"]),
        card("📊 Jumlah Draw", str(len(draws))),
    ]),
    unsafe_allow_html=True,
)

tab_dash, tab_base, tab_break, tab_wheel, tab_data = st.tabs(
    ["📊 Dashboard", "🔮 Base", "🧮 Formula Break", "🎡 Wheelpick", "📋 Data Draw"]
)

# ============================================================= DASHBOARD ===
with tab_dash:
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

# ===================================================================== BASE ===
with tab_base:
    section_title("🔮", "Base Draw — Kad Kongsi", "Gambar Base + satu senarai Top 10, siap muat turun/screenshot untuk Telegram.")

    if len(draws) < DEFAULT_RECENT_N:
        st.info(
            f"ℹ️ Perlu sekurang-kurangnya {DEFAULT_RECENT_N} draw untuk jana kad ini "
            f"(ada {len(draws)}). Tambah draw di tab **📋 Data Draw**."
        )
    else:
        with st.expander("⚙️ Tetapan"):
            bc1, bc2 = st.columns(2)
            base_recent_n = bc1.slider(
                "Jumlah draw terkini:", 20, len(draws), min(DEFAULT_RECENT_N, len(draws)), 5, key="base_n"
            )
            base_rank_range = bc2.select_slider(
                "Julat rank digit:", options=list(range(1, 11)), value=DEFAULT_RANK_RANGE, key="base_rank"
            )
            bc3, bc4 = st.columns(2)
            base_lot = bc3.text_input("Nilai Lot:", value="0.10", key="base_lot")
            base_score_n = bc4.slider(
                "Draw untuk kira skor Top 10:",
                min(10, len(draws)), len(draws), min(DEFAULT_RECENT_N, len(draws)), 5, key="base_score_n",
            )
            result_handle = st.text_input("Channel/Result handle:", value="@Breakcode4d", key="base_result_handle")

        try:
            base = generate_break_base(draws, recent_n=base_recent_n, rank_range=base_rank_range)
        except ValueError as e:
            st.error(str(e))
            base = None

        if base:
            kombinasi_utama = "".join(p[0] for p in base)
            date_label = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).strftime("%d/%m")
            rank_start, rank_end = base_rank_range

            png_bytes = render_base_image(base, rank_start, rank_end, kombinasi_utama, date_label, result_handle)
            st.image(png_bytes, use_container_width=True)
            st.download_button(
                "🖼️ Muat Turun Gambar Base (PNG)",
                data=png_bytes,
                file_name=f"base_{date_label.replace('/', '-')}.png",
                mime="image/png",
                key="dl_base_png",
            )
            st.caption("Tekan lama / klik kanan gambar di atas untuk terus simpan atau screenshot.")

            combos = generate_wheel_combos(base, lot=base_lot)
            top10 = rank_combos(combos, draws, recent_n=base_score_n, top_n=10)
            st.markdown(gold_top10_card(top10), unsafe_allow_html=True)

            top10_line = ", ".join(r["Nombor"] for r in top10)
            share_text = (
                f"🔮 {date_label} Breakcode Base Draw!!!!\n"
                f"🕹 Belian bebas ikut anda ibox/tegak dimana\u00b2 rumah (Recommended GD Lotto)\n\n"
                f"Result : {result_handle}\n"
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

# ========================================================== FORMULA BREAK ===
with tab_break:
    section_title("🧮", "Formula Break — Jana Base")
    st.markdown(
        '<div class="bc4d-note">Ambil digit <strong>rank ke-6 hingga ke-10</strong> paling kerap '
        "keluar bagi setiap posisi (P1–P4) — bukan digit yang paling 'panas'. Andaian: digit yang "
        "sudah agak sejuk ini berpotensi 'break' masuk giliran seterusnya.</div>",
        unsafe_allow_html=True,
    )

    if len(draws) < 20:
        st.warning("⚠️ Data draw terlalu sedikit (<20). Tambah draw di tab **📋 Data Draw** dahulu.")
    else:
        colA, colB = st.columns(2)
        recent_n = colA.slider(
            "Jumlah draw terkini:", 20, len(draws), min(DEFAULT_RECENT_N, len(draws)), 5, key="break_n"
        )
        rank_range = colB.select_slider(
            "Julat rank digit (1 = paling panas):",
            options=list(range(1, 11)),
            value=DEFAULT_RANK_RANGE,
            key="break_rank",
        )

        try:
            base = generate_break_base(draws, recent_n=recent_n, rank_range=rank_range)
            st.markdown("**🔢 Base Formula Break (boleh salin):**")
            st.code("\n".join(" ".join(p) for p in base), language="text")

            with st.expander("🔁 Backtest — uji prestasi sebenar"):
                bt_mode = st.radio(
                    "Kaedah:", ["Base Tunggal", "Base Gabungan (2 Base)"], horizontal=True, key="bt_mode"
                )
                rounds = st.slider("Bilangan draw lepas untuk diuji:", 5, 50, 10, 5, key="bt_rounds")
                if st.button("🚀 Jalankan Backtest", key="bt_run"):
                    if bt_mode == "Base Tunggal":
                        records, full_match, hit_rate = backtest_break(
                            draws, recent_n=recent_n, rounds=rounds, rank_range=rank_range
                        )
                    else:
                        records, full_match, hit_rate = backtest_combined(
                            draws, recent_n=recent_n, rounds=rounds, rank_range=rank_range
                        )
                    if records:
                        st.success(
                            f"🎯 Match penuh (4/4 posisi): {full_match} / {len(records)} draw  →  **{hit_rate}%**"
                        )
                        st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)
                    else:
                        st.warning("Data tidak mencukupi untuk backtest dengan tetapan ini.")
        except ValueError as e:
            st.error(str(e))

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
        ["Auto — Formula Break", "Gabung 2 Base (Hari ini + Semalam)", "Manual"],
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
    else:
        manual_base = st.text_area(
            "Masukkan Base Manual (4 baris, digit dipisah space):", height=120, key="wp_manual"
        )
        lines = [ln.strip().split() for ln in manual_base.strip().split("\n") if ln.strip()]
        if manual_base.strip() and len(lines) == 4 and all(lines):
            base_wp = lines
        elif manual_base.strip():
            st.error("❌ Format base tidak sah — perlu tepat 4 baris, setiap baris ada sekurang-kurangnya satu digit.")

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

        if st.button("🎰 Jana Wheelpick", key="wp_run"):
            arah = "kiri" if arah_wp == "Kiri→Kanan" else "kanan"
            combos = generate_wheel_combos(base_wp, lot=lot, arah=arah)
            st.info(f"Sebelum tapis: **{len(combos)}** kombinasi")

            filtered = filter_wheel_combos(
                combos, draws, no_repeat, no_triple, no_pair, no_ascend, use_history, sim_limit, likes, dislikes
            )
            st.success(f"✅ Selepas tapis: **{len(filtered)}** kombinasi")

            for i in range(0, len(filtered), 30):
                part = filtered[i : i + 30]
                st.markdown(f"**Bahagian {i // 30 + 1}:**")
                st.code("\n".join(part), language="text")

            if filtered:
                st.download_button(
                    "💾 Muat Turun Wheelpick",
                    data="\n".join(filtered).encode(),
                    file_name="wheelpick.txt",
                    mime="text/plain",
                )

                divider()
                section_title("🏆", "Top 10 Pilihan", f"Disusun ikut kekerapan sebenar digit P1–P4 dalam {score_n} draw terkini.")
                top10 = rank_combos(filtered, draws, recent_n=score_n, top_n=10)
                st.dataframe(pd.DataFrame(top10), use_container_width=True, hide_index=True)

                top10_text = "\n".join(f"{r['Nombor']}#####{r['Lot']}" for r in top10)
                st.code(top10_text, language="text")
                st.download_button(
                    "💾 Muat Turun Top 10",
                    data=top10_text.encode(),
                    file_name="wheelpick_top10.txt",
                    mime="text/plain",
                    key="dl_top10",
                )
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
