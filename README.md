# 🔮 Breakcode4D — GD Lotto 4D (Formula Break Edition)

Aplikasi web **Streamlit** untuk analisis corak & jana cadangan nombor **GD Lotto 4D**
(Malaysia), berdasarkan kaedah statistik kekerapan digit (**Formula Break**) dan
penjana kombinasi (**Wheelpick**).

https://gdlottox-3qwygdga3lcnsyjfd2mv7u.streamlit.app/

Ini adalah versi **bersih & fokus** daripada projek asal `gdlotto4d`. Strategi lain
(frequency, hybrid, polarity_shift, smartpattern, hitfq), modul AI, cross-analysis,
superbase, dan pautan promosi telah dibuang. Yang tinggal hanya perkara teras:

1. **📊 Dashboard** — insight ringkas draw terakhir, digit like/dislike & trek rekod ramalan
2. **🔮 Base** — pusat utama Formula Break: jana base, cadangan tetapan terbaik, kad kongsi & analisis lanjutan
3. **🔎 Semak Nombor** — semak sejarah satu nombor sasaran terhadap base Formula Break
4. **🎡 Wheelpick** — jana & tapis kombinasi 4D penuh daripada base (auto/manual/gabungan) + Top pilihan terbaik
5. **📋 Data Draw** — data sokongan (sejarah keputusan, tambah/kemas kini)

> ⚠️ Ini adalah alat **analisis statistik/corak sejarah** semata-mata — **bukan**
> jaminan keputusan. 4D adalah permainan nasib; mainlah secara bertanggungjawab.

## 🗂️ Struktur Projek

```
GdLottoX/
├── app.py                     # UI Streamlit utama (5 tab)
├── core/
│   ├── data_draw.py           # baca / tambah / kemas kini draw
│   ├── formula_break.py       # logik Formula Break, backtest, cadangan & ujian statistik
│   ├── wheelpick.py           # jana, tapis & ranking kombinasi wheelpick
│   └── predictions_log.py     # log ramalan forward-looking (base disimpan sebelum keputusan keluar)
├── assets/
│   ├── style.css               # tema visual custom (kad, chip, kad kongsi)
│   └── fonts/                  # fon custom untuk render Kad Kongsi (PNG)
├── .streamlit/
│   └── config.toml             # tema warna Streamlit (dark, aksen pink/magenta)
├── data/
│   └── draws.txt                # sejarah draw (format setiap baris: "YYYY-MM-DD NNNN")
└── requirements.txt
```

## 🧭 Bahagian Atas (Header)

Setiap kali app dibuka, bahagian paling atas memaparkan 4 kad ringkasan yang dikongsi
oleh semua tab:

- **⏳ Draw Seterusnya** — anggaran baki masa, dikira berdasarkan waktu keputusan
  **8:00 malam (waktu Malaysia)** sebagai penanda draw harian.
- **📅 Draw Terakhir** — tarikh draw paling baru dalam `data/draws.txt`.
- **🎯 Keputusan Terakhir** — nombor 4D bagi draw terakhir tersebut.
- **📊 Jumlah Draw** — jumlah keseluruhan rekod draw dalam data.

Jika tarikh draw terakhir sudah lebih 1 hari lapuk (tanda `draws.txt` belum
dikemas kini), app memaparkan amaran automatik dan mencadangkan tekan butang
**"Kemas Kini Draw"** atau tambah draw secara manual di tab **📋 Data Draw**.

## 🧮 Konsep Teras: Formula Break

Bagi setiap posisi nombor 4D (**P1–P4**), kekerapan setiap digit (0–9) dikira
daripada **N draw terkini** (`recent_n`, lalai 50), lalu disusun ikut rank 1
(paling kerap) hingga 10 (paling jarang). Formula Break mengambil digit
**rank ke-6 hingga ke-10** (`rank_range`, lalai 6–10) — bukan yang paling
"panas" — dengan andaian digit yang sudah sejuk sedikit berpotensi "break"
masuk giliran seterusnya. Kedua-dua N dan julat rank boleh dilaraskan terus
dari UI di tab **🔮 Base**.

**Base Gabungan (2 Base)**: pilihan untuk gabungkan base "hari ini" (draw
terkini) dengan base "semalam" (draw terkini tanpa draw paling akhir) — digit
unik daripada kedua-dua base dikumpul jadi satu senarai bagi setiap posisi
(susunan base pertama dikekalkan dahulu, diikuti digit baru dari base kedua
yang belum ada; tiada pendua). Contoh: `12345` + `23456` → `123456`.

**Backtest adil**: setiap ujian prestasi (backtest, cadangan N/julat,
chi-square, dsb.) sentiasa jana base untuk draw ke-*i* hanya daripada draw
**sebelum** draw ke-*i* — supaya tiada maklumat masa depan bocor ke dalam
ujian.

## 📑 Cara Kerja Setiap Tab

### 1. 📊 Dashboard

- **📥 Kemas Kini Draw Terkini** — butang untuk tarik keputusan terbaru terus
  dari sumber dalam talian (perlu sambungan internet semasa app dijalankan);
  guna fungsi `scrape_latest()` yang sama dengan tab Data Draw.
- **📌 Insight Draw Terakhir** — semakan digit demi digit (P1–P4) keputusan
  draw **terakhir** yang sudah keluar, terhadap:
  - **🧮 Base Tunggal (Formula Break)** — base dijana daripada draw
    *sebelum* draw terakhir, supaya semakan adil (base "tak tahu" keputusan
    yang disemak).
  - **🔗 Base Gabungan (2 Base)** — sama konsep, tapi guna base gabungan
    hari-ini + semalam yang turut dijana daripada draw sebelum draw terakhir.
  - Setiap digit P1–P4 ditanda ✅ (kena) atau ❌ (tak kena) mengikut sama ada
    ia wujud dalam base berkenaan.
- **👍 Like / Dislike Digit** — 3 digit paling kerap muncul ("Like") dan 3
  digit paling jarang muncul ("Dislike") dalam 30 draw terkini, dikira
  merentasi semua posisi (P1–P4) sekali gus. Nilai ini turut jadi nilai lalai
  untuk penapis Like/Dislike di tab Wheelpick.

*(Bahagian "📊 Rekod Ramalan Sebenar" turut wujud di tab ini untuk menjejak
ramalan forward-looking yang pernah dilog — tidak diterangkan secara detail
dalam dokumen ini.)*

### 2. 🔮 Base

Pusat utama untuk jana, uji, dan kongsi base Formula Break. Perlu sekurang-
kurangnya **20 draw** untuk mula. Semua bahagian dalam tab ini berkongsi
**SATU** set tetapan (tarikh, N, julat rank) supaya tak perlu ulang set
berasingan seperti versi lama.

- **🗓️ Tarikh Draw** — date picker; secara automatik dipilih tarikh draw
  **seterusnya** (belum keluar), tapi boleh ditukar ke mana-mana tarikh lain
  (lepas atau depan) untuk semak/jana balik base bagi hari tersebut. Semua
  base, kad, cadangan & backtest di bawah **hanya** guna draw sebelum tarikh
  yang dipilih.
- **⚙️ Tetapan Base** — slider **N** (jumlah draw terkini, minimum 20) dan
  select-slider **Julat rank digit** (lalai 6–10); dipakai serentak oleh
  semua bahagian di bawah.
- **🎯 Cadangan Tetapan Terbaik (N + Julat serentak)** (expander) — pilih
  beberapa calon saiz N dan bilangan draw lepas untuk diuji, lalu app
  jalankan backtest **sebenar** (bukan simulasi) bagi setiap gabungan
  N × julat rank (lebar sama), dan ranking ikut bilangan match penuh (4/4)
  sebenar. Keputusan terbaik dipaparkan berserta jadual perbandingan penuh
  dan butang **"✅ Guna ... Sekarang"** untuk terus set N & julat terbaik
  tanpa perlu taip manual.
- **🔢 Base** — base P1–P4 dipaparkan dalam kotak kod (boleh salin terus).
  Jika keputusan sebenar untuk tarikh dipilih sudah wujud, dipaparkan
  perbandingan digit demi digit (✅/❌); jika belum, base tersebut dianggap
  unjuran/ramalan dan boleh dilog (butang **"📌 Log Ramalan Ini"**) untuk
  rekod trek forward-looking.
- **🎴 Jana Kad Kongsi (Gambar)** (expander) — jana gambar PNG shareable
  (untuk Telegram/media sosial) daripada base semasa, dengan pilihan:
  - 6 gaya reka bentuk kad: **Gold (Asal)**, **Neon Arcade**,
    **Swiss Editorial**, **Emerald Casino**, **Retro Ticket**,
    **Soft Neumorphic**
  - Nilai lot, bilangan draw untuk kira skor Top 10, nama channel/result
    handle, dan senarai "nombor top hari ini" (hot digits) untuk ditonjolkan
    pada kad
  - "Kombinasi Utama" pada kad dipilih daripada kombinasi #1 dalam Top 10
    (skor kekerapan sebenar gabungan P1–P4) — bukan sekadar cantum digit
    rank-teratas tiap posisi secara berasingan, jadi lebih tepat
  - Gambar boleh dimuat turun (PNG), dan teks salin format Telegram turut
    disediakan (boleh dimuat turun sebagai `.txt`)
- **🔬 Analisis Lanjutan — Backtest, Chi-Square, Ensemble** (expander):
  - **🔁 Backtest** — uji prestasi sebenar Base Tunggal atau Base Gabungan
    terhadap X draw lepas (boleh laras 5–50), dibandingkan dengan
    **baseline rawak** (kebarangkalian tepat secara matematik base rawak
    dengan lebar sama akan match penuh) — untuk nilai sama ada Formula Break
    benar-benar ada *edge* berbanding tekaan rawak.
  - **🔍 Cari N Terbaik** — cuba beberapa calon N (julat rank dikekalkan
    tetap ikut tetapan semasa), ranking ikut match penuh sebenar; ada butang
    untuk terus pakai N terbaik.
  - **📐 Ujian Statistik Chi-Square** — uji sama ada taburan 10 digit (0–9)
    bagi setiap posisi P1–P4 dalam N draw terkini menyimpang secara
    signifikan (p<0.05) daripada taburan seragam/rawak sepenuhnya. p-value
    dianggar guna hampiran Wilson–Hilferty (tanpa perlu pakej `scipy`).
  - **🧬 Ensemble — Digit Stabil** — bandingkan base merentasi beberapa saiz
    N serentak (cth: 30, 50, 100) dan cari digit yang **kekal** dalam julat
    rank yang sama di semua saiz N tersebut — digit stabil sebegini kurang
    berkemungkinan cuma nois daripada saiz sampel yang dipilih secara
    sembarangan.

### 3. 🔎 Semak Nombor

Beza dengan tab Base (cadangan julat secara umum): di sini pengguna masukkan
**SATU nombor sasaran** (P1–P4) yang sudah difikirkan, dan app semak
bila/sejauh mana nombor tersebut pernah "muncul" dalam base sepanjang
sejarah. Perlu sekurang-kurangnya **20 draw**.

- **🔢 Nombor Sasaran** — input 4 digit dipisah ruang (cth: `1 2 3 4`),
  berserta tetapan N & julat rank sendiri (berasingan daripada tab Base),
  dan minimum bilangan padanan (1–4 padanan) untuk ditapis dalam senarai
  tarikh.
- **📜 Senarai Tarikh Sepadan** — imbas **sepanjang** sejarah draw (kaedah
  "as of" — base bagi setiap tarikh hanya dijana daripada draw sebelum
  tarikh itu, elak bocor maklumat masa depan) dan papar semua tarikh di mana
  nombor sasaran sepadan (≥ minimum padanan yang ditetapkan), berserta
  keputusan sebenar & label kedudukan yang padan.
- **🎯 Ramalan & Cadangan Base — Draw Akan Datang** — app cuba **semua**
  julat rank yang lebar sama (ikut lebar julat semasa) dan cari julat mana
  yang beri bilangan match penuh (4/4) **tertinggi** sepanjang sejarah bagi
  nombor sasaran tersebut. Sebab/alasan turut dipaparkan (perbandingan
  dengan jangkaan rawak murni, dan perbandingan dengan tetapan semasa
  pengguna kalau berbeza), berserta base sebenar (data terkini) menggunakan
  julat dicadangkan yang boleh terus dipakai.
- **Lihat perbandingan semua julat** (expander) — jadual penuh perbandingan
  setiap julat rank lebar sama.
- Keputusan carian dicache (`st.cache_data`) supaya lebih pantas bila
  tetapan yang sama diulang.

### 4. 🎡 Wheelpick

Jana & tapis kombinasi nombor 4D penuh daripada mana-mana base 4-posisi.

- **Arah susunan** — Kiri→Kanan (P1→P4) atau Kanan→Kiri (P4→P1); menentukan
  susunan posisi base semasa kombinasi dijana (base "dibalikkan" dahulu untuk
  mod Kanan→Kiri).
- **Digit Like / Dislike** — pra-isi automatik daripada 3 digit paling kerap
  / paling jarang (30 draw terkini), boleh diubah suai sendiri. Sebagai
  kriteria tapisan: kombinasi mesti mengandungi **sekurang-kurangnya satu**
  digit dari senarai Like (jika diisi), dan **ditolak sepenuhnya** jika
  mengandungi **mana-mana** digit dari senarai Dislike (jika diisi).
- **Sumber Base** — 4 pilihan:
  1. **Auto — Formula Break** — jana terus daripada base Formula Break
     terkini (boleh laras N); perlu ≥20 draw.
  2. **Gabung 2 Base (Hari ini + Semalam)** — sama konsep Base Gabungan
     (papar base hari ini, base semalam, dan base gabungan yang dipakai);
     perlu ≥21 draw.
  3. **Manual** — taip/tampal 4 baris base sendiri (digit dipisah ruang).
  4. **Gabung 2 Base (Manual)** — taip 2 set base sendiri (cth: satu dari
     channel lain, satu base sendiri) dan digabungkan sama konsep seperti
     mod #2.
- **⚙️ Tapisan Tambahan** (expander) — pilihan tapis kombinasi:
  - Buang digit ulang (semua 4 digit mesti unik)
  - Buang triple (3 digit sama)
  - Buang pair (ada tepat sepasang digit sama)
  - Buang menaik (nombor berurutan seperti 1234, 2345, ... 6789)
  - Buang nombor yang pernah keluar dalam sejarah
  - Had maksimum digit sama kedudukan berbanding draw terakhir (0–4)
  - Turut tapis ikut Like/Dislike digit di atas
- **🎰 Jana Wheelpick** — papar jumlah kombinasi sebelum & selepas tapis,
  senarai penuh dipecahkan dalam set 10 nombor, dan boleh dimuat turun
  (`.txt`, format `NNNN#####lot`).
- **🏆 Top Pilihan** — pilih 10/20/30/50/100/150/200 kombinasi **terbaik**
  daripada senarai tertapis, disusun ikut **skor kekerapan sebenar** setiap
  digit P1–P4 dalam N draw terkini (bukan rawak) — makin tinggi skor, makin
  "kuat" kombinasi tersebut berdasarkan corak terkini. Boleh dimuat turun
  dalam format "Set" (10/set) atau format lot penuh.

### 5. 📋 Data Draw

Sumber data mentah tunggal (`data/draws.txt`) yang digunakan oleh **semua**
tab lain.

- **➕ Tambah Draw Manual** — masukkan tarikh (`YYYY-MM-DD`) & nombor 4
  digit; app menolak jika format tak sah atau tarikh sudah wujud (elak
  pendua).
- **📥 Kemas Kini Automatik** — cuba tarik keputusan terkini secara automatik
  daripada gdlotto.net (perlu pakej `requests` + `beautifulsoup4` &
  sambungan internet semasa app dijalankan); mengisi jurang tarikh yang
  hilang hari demi hari, berdasarkan waktu keputusan 8:00 malam (waktu
  Malaysia) sebagai penentu tarikh terkini yang "sepatutnya" sudah keluar.
- **📜 Senarai Draw** — jadual semua draw (tersusun terbaru dahulu) dan
  butang muat turun `draws.txt` mentah.

## 🧩 Modul Teras (`core/`)

| Fail | Fungsi utama yang disediakan |
|---|---|
| `data_draw.py` | `load_draws`, `add_draw`, `scrape_latest`, `get_draw_countdown_from_last_8pm` |
| `formula_break.py` | `generate_break_base`, `check_against_base`, `combine_bases`, `backtest_break`, `backtest_combined`, `backtest_random_baseline`, `scan_digit_history`, `recommend_rank_range`, `recommend_rank_range_general`, `recommend_recent_n`, `recommend_base_config`, `chi_square_uniformity`, `ensemble_stable_digits` |
| `wheelpick.py` | `get_like_dislike_digits`, `generate_wheel_combos`, `filter_wheel_combos`, `rank_combos`, `pick_from_base` |
| `predictions_log.py` | `log_prediction`, `load_predictions`, `reconcile_predictions`, `prediction_summary` — enjin di sebalik fungsi log ramalan forward-looking |

## ▶️ Cara Jalankan

```bash
pip install -r requirements.txt
streamlit run app.py
```

Data draw sedia ada (`data/draws.txt`, sejarah dari 2020 sehingga kini) turut
disertakan supaya app boleh terus digunakan tanpa perlu tambah data dari
kosong. Guna tab **📋 Data Draw** untuk tambah draw baru secara manual, atau
cuba butang **"Kemas Kini Draw"** (perlu sambungan internet semasa app
dijalankan).

## ⚠️ Nota

Formula Break, Wheelpick, dan semua tool analisis (backtest, chi-square,
ensemble, cadangan N/julat) adalah alat analisis statistik/corak sejarah
semata-mata — **bukan** jaminan keputusan. 4D adalah permainan nasib;
mainlah secara bertanggungjawab.
