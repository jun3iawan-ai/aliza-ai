# Hasil Eksperimen Fase 3

Semua angka persen adalah PnL per trade setelah fee, slippage, dan funding. Wilson adalah interval 95%. `sample_small` berlaku bila N<30. Output mentah lengkap (termasuk breakdown setup×regime×side dan trades.csv) tersimpan di `/tmp/fase3-results/{e1,e2,e3,e4_support,holdout_final}` pada mesin run; cache data tetap di-ignore git.

## Baseline 5m (production vs tanpa RR/conf filter)

| Varian | N | Winrate (Wilson 95%) | Expectancy | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| production_filters | 968 | 13,53% [11,52–15,83] | −0,3604% | 0,7110 | −354,44% |
| no_rr_conf_filters | 1003 | 14,06% [12,04–16,35] | −0,3666% | 0,7086 | −367,74% |

MAE baseline: dari 131 trade WIN, 3 (2,29%) sempat MAE ≤−1,5%; MAE WIN terburuk −1,6580%, median −0,5362%.

## TUNE — E1 ATR(14) (SL = multiplier × ATR)

| Konfigurasi | N | WR | Expectancy | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| ATR 1,0× | 279 | 17,92% [13,87–22,85] | −0,3273% | 0,7737 | −104,65% |
| ATR 1,5× | 66 | 22,73% [14,29–34,17] | +0,0615% | 0,9775 | −28,82% |
| ATR 2,0× | 3 | 0% | −1,0929% | 0 | −3,74% |
| ATR 2,5× | 1 | 0% | −2,3405% | 0 | −2,34% |

ATR 1,5× tidak memenuhi N≥200; kandidat eligible untuk tahap berikutnya adalah 1,0×.

## TUNE — E2 (berbasis ATR 1,0×)

| Konfigurasi | N | WR | Expectancy | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| Konfirmasi candle berikutnya | 90 | 15,56% | −0,5735% | 0,5949 | −67,34% |
| Hapus Overbought Rejection | 131 | 17,56% | −0,4135% | 0,7166 | −72,00% |
| Hapus Oversold Bounce | 174 | 18,97% | −0,1893% | 0,8503 | −67,82% |
| Support-distance ≤1% | 278 | 17,99% [13,92–22,93] | −0,3199% | 0,7776 | −102,27% |

## TUNE — E3 (ATR 1,0× + support filter)

| TP/time-stop | N | WR | Expectancy | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| Resistance / 3 hari | 278 | 12,59% | −0,3582% | 0,5747 | −102,04% |
| Resistance / 7 hari | 278 | 17,99% | −0,3199% | 0,7776 | −102,27% |
| 2×ATR / 3 hari | 0 | — | 0% | 0 | 0% |
| 2×ATR / 7 hari | 0 | — | 0% | 0 | 0% |
| 3×ATR / 3 hari | 751 | 18,64% [16,02–21,58] | +0,0064% | 0,8105 | −139,01% |
| 3×ATR / 7 hari | 743 | 23,42% [20,52–26,60] | −0,1381% | 0,9260 | −215,83% |

N=0 pada 2×ATR terjadi karena RR=2 ditolak production filter RR≥3.

## TUNE — E4 (ATR 1,0× + support filter)

| Konfigurasi | N | WR | Expectancy | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| Pullback Short funding>0 | 273 | 18,32% | −0,2854% | 0,7962 | −93,65% |
| RR2/conf60 | 278 | 17,99% | −0,3199% | 0,7776 | −102,27% |
| RR2/conf70 | 278 | 17,99% | −0,3199% | 0,7776 | −102,27% |
| RR3/conf60 | 278 | 17,99% | −0,3199% | 0,7776 | −102,27% |
| RR3/conf70 | 278 | 17,99% | −0,3199% | 0,7776 | −102,27% |

Threshold RR/conf tidak mengubah hasil; funding-positive memperbaiki expectancy relatif baseline tetapi masih negatif.

## Walk-forward empat bagian kronologis (TUNE)

Pembagian empat interval sama panjang. Kandidat E3 3×ATR/3 hari: Q1 N=217/E=−0,3071%/PF=0,6693; Q2 N=185/E=+1,0550%/PF=1,3028; Q3 N=127/E=+0,8672%/PF=1,0688; Q4 N=222/E=−1,0533%/PF=0,4079. Kandidat E2 support: Q1 N=62/E=−0,4423%; Q2 N=51/E=−0,1140%; Q3 N=40/E=+1,0797%; Q4 N=125/E=−0,7912%. Keduanya tidak stabil sepanjang TUNE.

## HOLDOUT (sekali per kandidat final)

Kandidat dipilih berdasarkan expectancy TUNE tertinggi dengan N≥200: E3 3×ATR/3 hari dan E2 support-distance. Hasil:

| Kandidat | N | WR (Wilson 95%) | Expectancy | PF | Max DD | Profit coin terbesar | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| E3 3×ATR / 3 hari | 149 | 26,17% [19,78–33,77] | +1,0753% | 1,4769 | −22,83% | WLD 45,2% | **LOLOS** |
| E2 support-distance | 72 | 22,22% [14,17–33,09] | +0,3105% | 1,0652 | −30,08% | XRP 74,1% | **GAGAL** (N<80, PF≤1,15) |

E3 memenuhi seluruh kriteria numerik, termasuk konsentrasi profit coin terbesar <50%; namun walk-forward TUNE yang tidak stabil dan N holdout 149 tetap memerlukan validasi lanjutan. Hasil ini adalah usulan riset, bukan izin deploy.

## Breakdown setup × regime × side kandidat E3

| Periode | Setup | Regime | Side | N | WR | Expectancy | PF |
|---|---|---|---|---:|---:|---:|---:|
| TUNE | OVERBOUGHT REJECTION | DOWNTREND | SHORT | 1 | 0% | +1,8154% | 0 |
| TUNE | OVERBOUGHT REJECTION | RANGE | SHORT | 230 | 20,87% | −0,0962% | 0,8518 |
| TUNE | OVERSOLD BOUNCE | RANGE | LONG | 290 | 16,21% | +0,1542% | 0,8032 |
| TUNE | PULLBACK LONG | TREND | LONG | 96 | 15,63% | −0,0889% | 0,7370 |
| TUNE | PULLBACK SHORT | DOWNTREND | SHORT | 105 | 19,05% | −0,7354% | 0,5680 |
| TUNE | PULLBACK SHORT | TREND | SHORT | 29 | 34,48% | +2,2827% | 2,1403 |
| HOLDOUT | OVERBOUGHT REJECTION | DOWNTREND | SHORT | 4 | 25,00% | +1,0687% | 1,6350 |
| HOLDOUT | OVERBOUGHT REJECTION | RANGE | SHORT | 45 | 33,33% | +1,1139% | 1,5917 |
| HOLDOUT | OVERSOLD BOUNCE | RANGE | LONG | 39 | 20,51% | +0,6019% | 1,1479 |
| HOLDOUT | PULLBACK LONG | TREND | LONG | 15 | 26,67% | +0,2801% | 1,0520 |
| HOLDOUT | PULLBACK SHORT | DOWNTREND | SHORT | 37 | 27,03% | +2,2239% | 2,4836 |
| HOLDOUT | PULLBACK SHORT | TREND | SHORT | 9 | 11,11% | −0,4602% | 0,5254 |

Sel grup dengan N<30 (misalnya PULLBACK SHORT/TREND di TUNE dan grup DOWNTREND tertentu di holdout) adalah sampel kecil dan tidak konklusif.
