# 🔮 Breakcode4D — Formula Break Edition

Versi **bersih & fokus** daripada projek asal `gdlotto4d`. Semua strategi
lain (frequency, hybrid, polarity_shift, smartpattern, hitfq), modul AI,
cross-analysis, superbase, dan pautan promosi telah dibuang. Yang tinggal
hanya perkara teras:

1. **🧮 Formula Break** — jana base P1–P4 + backtest prestasi sebenar
2. **🎡 Wheelpick** — jana & tapis kombinasi 4D daripada base (auto, gabung
   hari ini + semalam, atau manual) + Top 10 pilihan terbaik
3. **📋 Data Draw** — data sokongan (sejarah keputusan, tambah/kemas kini)
4. **📊 Dashboard** — insight ringkas draw terakhir & digit like/dislike

## 🗂️ Struktur Projek

```
breakcode4d/
├── app.py                  # UI Streamlit utama (4 tab)
├── core/
│   ├── data_draw.py         # baca/tambah/kemas kini draw
│   ├── formula_break.py     # logik Formula Break + backtest
│   └── wheelpick.py         # jana & tapis kombinasi wheelpick
├── assets/
│   └── style.css            # tema visual custom
├── .streamlit/
│   └── config.toml          # tema warna Streamlit
├── data/
│   └── draws.txt            # sejarah draw (disertakan, 545 rekod)
└── requirements.txt
```

## 🧮 Konsep Formula Break

Bagi setiap posisi (P1–P4), kekerapan setiap digit (0–9) dikira daripada
*N* draw terkini, lalu disusun ikut rank 1 (paling kerap) hingga 10
(paling jarang). Formula Break mengambil digit **rank ke-6 hingga
ke-10** — bukan yang paling "panas" — dengan andaian digit yang sudah
sejuk sedikit berpotensi "break" masuk giliran seterusnya. Julat rank
ini boleh dilaraskan terus dari UI (default 6–10, sama seperti projek
asal).

Tab **Backtest** dalam Formula Break menguji base ini terhadap draw
lepas secara adil — base untuk draw ke-*i* hanya dijana daripada draw
**sebelum** draw ke-*i*, supaya tiada maklumat masa depan bocor ke
dalam ujian.

## 🔗 Gabung 2 Base (Wheelpick)

Di tab Wheelpick, pilihan sumber base "Gabung 2 Base (Hari ini +
Semalam)" akan jana base hari ini (semua draw terkini) dan base
semalam (draw terkini tanpa draw paling akhir), kemudian gabungkan
kedua-duanya ikut posisi (P1–P4) — digit unik dari kedua-dua base
dikumpul jadi satu senarai (tiada pendua), cth: `12345` + `23456` →
`123456`.

## ▶️ Cara Jalankan

```bash
pip install -r requirements.txt
streamlit run app.py
```

Data draw sedia ada (`data/draws.txt`) dari projek asal turut
disertakan supaya aplikasi boleh terus digunakan. Guna tab **Data
Draw** untuk tambah draw baru secara manual, atau cuba butang "Kemas
Kini Draw" (perlukan sambungan internet semasa dijalankan).

## ⚠️ Nota

Formula Break & Wheelpick adalah alat analisis statistik/corak
sejarah semata-mata — bukan jaminan keputusan. 4D adalah permainan
nasib; mainlah secara bertanggungjawab.
