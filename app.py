"""
app.py — Breakcode4D (versi ringkas)
--------------------------------------
Fokus penuh pada:
  1. Formula Break  — jana & uji base P1–P4
  2. Wheelpick      — jana & tapis kombinasi 4D
  3. Data Draw      — data sokongan (sejarah keputusan)
"""

from pathlib import Path

import pandas as pd
import streamlit as st

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


# ================================================================== PAGE ===
load_css()

st.markdown(
    """
    <div class="bc4d-header">
        <div class="emoji">🔮</div>
        <div>
            <h1>Breakcode4D — Formula Break</h1>
            <p>Fokus penuh pada Formula Break &amp; Wheelpick Generator untuk 4D.</p>
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

tab_dash, tab_break, tab_wheel, tab_data = st.tabs(
    ["📊 Dashboard", "🧮 Formula Break", "🎡 Wheelpick", "📋 Data Draw"]
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
