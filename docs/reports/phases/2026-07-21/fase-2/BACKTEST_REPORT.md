# BACKTEST_REPORT — Evaluasi 4 Setup TradingBrain

Tanggal run: 21 Juli 2026  
Periode: 2024-07-21 00:00 UTC sampai 2026-07-21 23:59 UTC  
Coin: BTC, ETH, BNB, SOL, XRP, ADA, SUI, ARB, PEPE, WLD, TAO  
Notional: 100 USDT/trade; fee 0,1%/sisi; slippage 0,05%/sisi.  
Resolusi exit: 1h fallback untuk seluruh baseline karena 5m tidak diunduh massal.  
Commit data/config: `218fb1c6`.

## Ringkasan agregat

| Varian | N | Win | Loss | Winrate (Wilson 95%) | Expectancy/trade | Profit factor | Max drawdown seri |
|---|---:|---:|---:|---:|---:|---:|---:|
| Production RR≥3, confidence≥70 | 1.147 | 159 | 977 | 13,86% [11,98–15,98%] | -0,3424% | 0,7252 | -397,83% |
| Tanpa filter RR/conf | 1.205 | 179 | 1.014 | 14,85% [12,96–16,97%] | -0,3340% | 0,7306 | -402,50% |

Metrik memasukkan trade `EXPIRED` dalam N, sedangkan WIN/LOSS hanya menghitung outcome tersebut. Semua sel agregat memiliki sampel >30; grouping kecil diberi label “sampel kecil — tidak konklusif”.

## Production filter per setup

| Setup | N | Winrate | Wilson 95% | Expectancy % | Profit factor | Avg win % | Avg loss % | Median durasi |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OVERSOLD BOUNCE | 483 | 14,29% | 11,45–17,69% | -0,4322 | 0,6994 | 7,4272 | -1,7959 | 3 jam |
| OVERBOUGHT REJECTION | 372 | 10,48% | 7,76–14,01% | -0,4002 | 0,6453 | 7,3818 | -1,3479 | 3 jam |
| PULLBACK LONG | 110 | 17,27% | 11,35–25,41% | -0,1682 | 0,8465 | 6,0033 | -1,4971 | 6 jam |
| PULLBACK SHORT | 182 | 17,58% | 12,74–23,77% | -0,0911 | 0,9011 | 6,1076 | -1,4655 | 7 jam |

Interpretasi: tidak ada setup yang expectancy positif atau profit factor >1 pada agregat 2 tahun. PULLBACK SHORT paling dekat breakeven, tetapi tetap negatif dan bukan dasar mematikan setup tanpa validasi resolusi 5m.

## Walk-forward agregat per kuartal

| Kuartal | N | Winrate | Expectancy % | Profit factor | Catatan |
|---|---:|---:|---:|---:|---|
| Q1 | 413 | 13,56% | -0,3952 | 0,7007 | Negatif |
| Q2 | 210 | 20,00% | +0,2224 | 1,1421 | Positif sementara |
| Q3 | 336 | 9,82% | -0,6602 | 0,5009 | Terburuk |
| Q4 | 188 | 14,89% | -0,2894 | 0,7696 | Negatif |

Tidak ada setup yang stabil positif lintas kuartal. Q2 positif secara agregat, tetapi Q1/Q3/Q4 negatif; ini bukan bukti edge stabil.

## Temuan

1. Biaya dan slippage penting: median PnL sekitar -1,30% sampai -1,80% pada loss, sedangkan win rata-rata 6–7%; frekuensi stop-out jauh terlalu tinggi untuk menutupnya.
2. Filter RR≥3/confidence≥70 mengurangi N dari 1.205 menjadi 1.147, tetapi tidak memperbaiki expectancy secara material (-0,3340% menjadi -0,3424%).
3. OVERSOLD BOUNCE dan OVERBOUGHT REJECTION adalah dua setup terlemah secara agregat.
4. PULLBACK SHORT memiliki expectancy terbaik relatif (-0,0911%) dan profit factor 0,9011, tetapi tetap belum positif.
5. Hasil resolusi 1h tidak boleh dianggap validasi final microstructure 5m. Funding historis juga belum tersedia sehingga seluruh short menggunakan fallback funding.

## Kandidat eksperimen Fase 3 (rekomendasi saja, tidak diterapkan)

- Uji SL adaptif ATR untuk OVERSOLD BOUNCE: loss expectancy -0,4322% dan avg loss -1,7959% menunjukkan stop tetap 1,5% sering tersentuh; ukur adverse excursion sebelum arah benar.
- Uji filter volatilitas/regime untuk OVERBOUGHT REJECTION: expectancy -0,4002% dan PF 0,6453; validasi apakah setup hanya layak pada RANGE tertentu.
- Uji entry/exit intrabar 5m dengan TP/SL ordering aktual dan funding historis; baseline 1h dapat mengubah urutan wick dan outcome.
- Uji pengurangan frekuensi sinyal PULLBACK SHORT dengan cooldown/market regime yang lebih ketat hanya sebagai eksperimen terpisah; setup ini paling dekat breakeven tetapi PF masih <1.
- Uji threshold RR/confidence sebagai eksperimen walk-forward terpisah, bukan tuning in-sample; baseline menunjukkan filter saat ini belum memberi edge.
- Tambahkan data Fear & Greed/whale historis atau nyatakan regime proxy sebagai fitur ablation agar pengaruh proxy dapat diukur.

Kesimpulan: berdasarkan data 2 tahun 11 coin, empat setup belum menunjukkan expectancy positif setelah biaya. Tidak ada parameter produksi yang diubah berdasarkan hasil ini.
