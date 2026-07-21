# ROBUSTNESS_RESULTS — E3 (holdout 21 Januari–21 Juli 2026)

Konfigurasi dibekukan sebelum pengujian: SL 1,0×ATR(14) 4h, filter Oversold Bounce harga ≤ support×1,01, TP 3×ATR, time-stop 3 hari, production RR/conf filter tetap aktif, fee/slippage/funding simulator produksi. Holdout berisi 149 trade pada 21 coin core (coin tanpa kandidat tetap dilaporkan N=0).

## 1. Bootstrap expectancy (10.000×)

Seed deterministik `20260721`. Resampling dengan replacement atas seluruh 149 trade (termasuk expired, konsisten aggregate_metrics): expectancy observasi **+1,0753%**, CI bootstrap 95% **[+0,3514%; +1,8382%]**. Batas bawah >0: **YA**.

## 2. Exclude-WLD

Tanpa WLD: N=136, winrate 23,53% (Wilson 17,19–31,32%), expectancy **+0,6457%**, PF **1,1719**, max DD −22,83%. Arah hasil tetap positif, tetapi PF turun di bawah 1,2; hasil tidak hanya bergantung pada WLD namun WLD tetap menyumbang kontribusi berarti.

## 3. Stress biaya

Slippage dasar 0,05% per sisi. Pengujian memakai 0,10% (2×) dan 0,15% (3×) per sisi, fee/funding tetap.

| Slippage | N | Expectancy | PF | Max DD |
|---|---:|---:|---:|---:|
| 0,05%/sisi (baseline) | 149 | +1,0753% | 1,4769 | −22,83% |
| 0,10%/sisi (2×) | 149 | +0,9741% | 1,3995 | −24,61% |
| 0,15%/sisi (3×) | 149 | +0,8729% | 1,3278 | −26,49% |

Expectancy **belum negatif pada level 3×**. Level lebih tinggi tidak termasuk grid yang ditetapkan sehingga tidak diekstrapolasi.

## 4. Rolling walk-forward (8 jendela kronologis)

Jendela sama panjang atas dua tahun 21 Juli 2024–21 Juli 2026; setiap window memakai data masa lalu yang tersedia sebelum timestamp sinyal.

| Window | N | Expectancy | PF | Status |
|---:|---:|---:|---:|---|
| 1 | 175 | −0,6825% | 0,5983 | negatif |
| 2 | 132 | +1,0730% | 1,2490 | positif |
| 3 | 95 | +1,2172% | 1,3399 | positif |
| 4 | 75 | +1,5808% | 1,4460 | positif |
| 5 | 141 | −0,8423% | 0,4433 | negatif |
| 6 | 127 | −0,7364% | 0,4966 | negatif |
| 7 | 84 | +1,3340% | 1,6106 | positif |
| 8 | 79 | +0,2077% | 0,8703 | positif |

**5/8 positif** (ambang “cukup sehat”), tetapi tiga window loss besar menunjukkan ketergantungan regime.

## 5. Per-coin holdout

| Coin | N | Expectancy | PF | Keterangan |
|---|---:|---:|---:|---|
| ADA | 22 | +0,5059% | 1,2004 | sampel kecil |
| ARB | 22 | −0,3617% | 0,7665 | sampel kecil |
| BNB | 16 | −0,5207% | 0,4219 | sampel kecil |
| BTC | 16 | +0,4304% | 0,9279 | sampel kecil |
| ETH | 20 | +1,1112% | 1,1953 | sampel kecil |
| PEPE | 18 | +0,8373% | 1,2625 | sampel kecil |
| SOL | 11 | +1,6478% | 2,1802 | sampel kecil |
| SUI | 12 | +1,8510% | 2,3779 | sampel kecil |
| TAO | 19 | +0,4295% | 1,2276 | sampel kecil |
| WLD | 26 | +2,2753% | 1,3742 | sampel kecil |
| XRP | 17 | −0,1268% | 0,7104 | sampel kecil |

Coin dengan outcome: **8 positif dari 11**; 10 coin core lain tidak menghasilkan trade pada holdout (N=0), sehingga bukan bukti profit maupun loss.

## 6. Sanity bias seleksi (post-hoc, bukan dasar promosi)

| Kandidat post-hoc | N | Expectancy | PF | Verdict kalibrasi |
|---|---:|---:|---:|---|
| E3 3×ATR / 7 hari | 146 | +0,4447% | 1,1736 | positif, PF di bawah kriteria 1,15? **LOLOS PF numerik**, namun bukan pemenang yang dipilih |
| ATR 1,5× (E1) | 18 | −0,6372% | 0,6885 | sampel kecil; tidak konklusif |

E3 3×ATR/7 hari ikut terlihat positif karena diuji setelah melihat grid; angka ini hanya mengukur kemudahan grid “lolos”, bukan validasi independen. Catatan: PF 1,1736 sebenarnya di atas ambang 1,15; N=146 juga di atas 80, tetapi konfigurasi tetap post-hoc dan tidak dipromosikan.

## Verdict Bagian A: CAMPURAN

Sinyal robustness kuat pada bootstrap (CI seluruhnya positif), tetap positif setelah WLD dikeluarkan, dan bertahan terhadap slippage 3×. Namun PF tanpa WLD turun ke 1,1719, hanya 5/8 window positif, dan tiga window negatif dengan PF rendah; sebagian besar breakdown per coin masih N<30. E3 **belum dapat disebut robust lintas-regime**, tetapi juga tidak rapuh. Shadow minimal enam minggu diperlukan sebelum keputusan promosi.
