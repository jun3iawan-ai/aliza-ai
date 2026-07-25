# Laporan — Perluas Circuit Breaker ke Broadcast Sinyal Produksi

**Tanggal:** 25 Juli 2026
**Branch:** `feat/drawdown-gate-broadcast` (dibuat dari `main`, sudah termasuk `db0d4e0` — learning loop live data)
**Status:** **BELUM di-merge/deploy** — implementasi + test saja, menunggu review sebelum merge (perubahan ini memengaruhi perilaku sinyal produksi yang benar-benar dikirim ke user).

Konteks: audit sebelumnya menemukan `drawdown_protector.check_drawdown()` (ambang `LOSS_STREAK_THRESHOLD=3`) sudah membaca data live sejak fix `db0d4e0`, tapi hanya menggerbangi perintah manual `/entry` — tidak menyentuh broadcast `[TRADE SIGNAL]` otomatis. Tujuan gap ini: begitu 3 LOSS beruntun untuk `source='deterministic'`, jeda pengiriman `[TRADE SIGNAL]` baru sampai streak-nya reset oleh WIN berikutnya.

---

## Langkah 0 — Diagnosis & Keputusan

### 0.1 Fungsi dispatch persis (dikonfirmasi ulang, file:line saat ini)

- `_dispatch_and_record_deterministic_signal()` — `interfaces/telegram_bot.py:6739` (sebelum edit; nomor baris bergeser sedikit dari audit sebelumnya karena ada penambahan import `check_drawdown`, tapi fungsi dan strukturnya sama).
- Dipanggil dari `scan_for_signals()` di dalam `snapshot_job()`: `interfaces/telegram_bot.py:6934-6937` (sebelum edit) — `sig = scan_for_signals(); if sig: await _dispatch_and_record_deterministic_signal(sig, chat_id)`.
- Gateway bersama: `engine/signal_engine.py:process_signal()` (baris 256 sebelum edit) — dipakai juga oleh auto-alert, system halt/recovery, dan (berdasarkan pola yang sama) sinyal `llm`/advisory. **Bukan** fungsi khusus deterministic saja.

### 0.2 Titik pemanggilan breaker

`can_send_signal()` (dedup TTL 15 menit, `engine/trading/signal_engine.py:84-91`, `SIGNAL_TTL_SECONDS=900`) dicek di dalam `process_signal()` (`engine/signal_engine.py:301` sebelum edit), **sebelum** macro-gateway dan **sebelum** `safe_dispatch()`. Supaya konsisten ("DI TITIK YANG SAMA atau tepat sebelum dispatch"), breaker baru diletakkan **di dalam `process_signal()` itu sendiri, tepat sebelum baris `safe_dispatch()`** — yaitu setelah dedup+risk+macro-gateway sudah lolos, bukan sebelum semua gate lain. Ini dilakukan lewat parameter baru `suppress_dispatch: bool = False` pada `process_signal()`:

```python
if suppress_dispatch:
    logger.info(f"[TRADE SIGNAL] SUPPRESSED (dispatch withheld) {key} from {src}")
    return True

from interfaces.telegram_bot import safe_dispatch
sent = await safe_dispatch(out_msg, chat_id=chat_id, force=force)
...
```
(`engine/signal_engine.py:339-350`)

**Kenapa di dalam `process_signal()`, bukan di `_dispatch_and_record_deterministic_signal()` sebelum memanggilnya sama sekali:** kalau breaker dicek di luar dan sinyal yang breaker-aktif langsung di-skip tanpa lewat `process_signal()`, sinyal itu juga akan melewati dedup TTL, risk-manager (`validate_signal_risk`), dan macro-gateway — berarti kita berisiko mencatat sinyal yang sebenarnya TIDAK akan lolos gate lain (mis. ditolak risk manager) seolah-olah itu sinyal produksi valid yang cuma "dijeda". Dengan menaruh breaker di titik yang sama seperti dedup (di dalam `process_signal()`, setelah gate lain lolos), sinyal yang direkam sebagai `SUPPRESSED` dijamin sinyal yang **benar-benar akan dikirim** kalau breaker tidak aktif — bukan sinyal yang sudah gugur di gate lain.

`process_signal()` sendiri **tidak** diberi pengetahuan soal `drawdown_protector` — ia cuma menerima flag generik `suppress_dispatch`, dihitung oleh pemanggil (`_dispatch_and_record_deterministic_signal`). Ini menjaga `process_signal()` tetap generik dan tidak bocor pengetahuan spesifik-breaker ke gateway yang dipakai banyak jenis sinyal lain.

### 0.3 Keputusan: tetap record, skip dispatch — **diikuti sesuai rekomendasi prompt**

`_dispatch_and_record_deterministic_signal()` sekarang memanggil `check_drawdown()` sendiri (satu kali per sinyal terdeteksi), lalu meneruskan hasilnya sebagai `suppress_dispatch=breaker_active` ke `process_signal()`. Karena `process_signal()` dengan `suppress_dispatch=True` tetap mengembalikan `True` (menandakan "lolos semua gate, cuma dispatch ditahan"), kode perekaman (`record_signal(...)`) di `_dispatch_and_record_deterministic_signal()` **tetap jalan seperti biasa** — hanya field `dispatch_status` yang dibedakan: `'SUPPRESSED'` (bukan `'SENT'`) supaya baris ini bisa dibedakan dari sinyal yang benar-benar sampai ke user, sambil tetap ikut dihitung `status`/`pnl_pct` oleh `signal_check_job` seperti sinyal lain (kontinuitas winrate/statistik terjaga, sesuai rekomendasi Langkah 0.3 di prompt).

---

## Item Implementasi

### 1. Suppress dispatch, tetap record — `interfaces/telegram_bot.py`

`_dispatch_and_record_deterministic_signal()` diubah:
```python
breaker_active = False
loss_streak = None
if check_drawdown is not None:
    try:
        dd = check_drawdown()
        breaker_active = not dd.get("trading_allowed", True)
        loss_streak = dd.get("loss_streak")
    except Exception as dd_err:
        logging.debug("drawdown check failed, defaulting to allowed: %s", dd_err)

sent = await process_signal(
    key, uni, format_signal_message(uni),
    chat_id=chat_id,
    suppress_dispatch=breaker_active,
)
if not sent:
    return False

if breaker_active:
    logging.info(
        "[TRADE SIGNAL] SUPPRESSED — drawdown breaker active, loss_streak=%s coin=%s setup=%s",
        loss_streak, sig.get("coin"), sig.get("setup"),
    )
...
sig_to_record["dispatch_status"] = "SUPPRESSED" if breaker_active else "SENT"
```
Kegagalan `check_drawdown()` (exception apa pun) **fail-open** ke `breaker_active=False` — konsisten dengan `drawdown_protector.check_drawdown()` sendiri yang juga fail-open (`{"trading_allowed": True}` pada exception), supaya bug di breaker tidak pernah menghentikan seluruh pengiriman sinyal produksi.

Import baru (opsional, try/except seperti pola lain di file ini):
```python
try:
    from engine.portfolio.drawdown_protector import check_drawdown
except ImportError:
    check_drawdown = None
```

### 2. Notifikasi transisi — persisted, satu kali per transisi

Fungsi baru `_notify_drawdown_breaker_transition(chat_id)` (`interfaces/telegram_bot.py`), dipanggil setiap siklus `snapshot_job` (~60 detik) **sebelum** blok "High probability trade", supaya transisi tetap terdeteksi tepat waktu walau `scan_for_signals()` tidak mengembalikan sinyal baru di siklus itu (mis. streak ditutup oleh `signal_check_job` di antara dua deteksi TradingBrain):

```python
async def _notify_drawdown_breaker_transition(chat_id) -> None:
    if check_drawdown is None:
        return
    dd = check_drawdown()
    active_now = not dd.get("trading_allowed", True)
    was_active = bool(ngov.get_value("drawdown_breaker", "active", False))
    if active_now == was_active:
        return
    ngov.set_value("drawdown_breaker", "active", active_now)
    msg = DRAWDOWN_BREAKER_ACTIVATED_MSG if active_now else DRAWDOWN_BREAKER_RESET_MSG
    await safe_dispatch(msg, chat_id=chat_id, force=True)
```

State "sudah dinotifikasi aktif/tidak" disimpan lewat `engine.alerts.notification_governor` (`get_value`/`set_value`, namespace `"drawdown_breaker"`, key `"active"`) — infrastruktur **yang sudah ada**, dipakai juga oleh cooldown shadow_e3 dan checker noise lain. Ini persisted ke `data/alert_cooldown_state.json`, tahan restart proses (bukan variabel modul biasa yang hilang tiap restart, seperti pola `CB_ALERT_SENT` untuk circuit breaker snapshot yang justru TIDAK persisted). Tidak ada file/mekanisme penyimpanan baru yang ditulis — murni pakai ulang.

Dipanggil di `snapshot_job()`:
```python
try:
    await _notify_drawdown_breaker_transition(context.bot_data.get("chat_id"))
except Exception as dd_notify_err:
    logging.debug("Drawdown breaker transition notice error: %s", dd_notify_err)
```

### 3. Scope — HANYA deterministic

Breaker **tidak** disentuh di `engine/shadow/e3_shadow.py` atau jalur `_run_shadow_e3()` sama sekali — tidak ada satu baris pun ditambahkan di sana. `suppress_dispatch` hanya pernah di-set `True` dari **satu titik**: `_dispatch_and_record_deterministic_signal()` (dikonfirmasi lewat `grep -rn "suppress_dispatch" --include="*.py" .` — cuma 1 call site di luar definisi parameternya sendiri). Sinyal `llm` (SARAN SPOT/FUTURES) yang memanggil `process_signal()` langsung tanpa argumen `suppress_dispatch` otomatis memakai default `False` — tidak terpengaruh apa pun status breaker.

### 4-5. Tidak diubah (sesuai instruksi)

`check_drawdown()`, `LOSS_STREAK_THRESHOLD=3` (`engine/portfolio/drawdown_protector.py`) — **nol perubahan**, file ini tidak ada di diff. Perintah `/entry` (`portfolio_ai_engine.evaluate_trade()`) — juga nol perubahan, tetap menggerbangi seperti sebelumnya.

---

## Ringkasan Perubahan File

```
 engine/signal_engine.py         | 11 +++++++
 interfaces/telegram_bot.py      | 74 ++++++++++++++++++++++++++++++++++++++++++++--
 tests/test_drawdown_broadcast_gate.py | (baru, 11 test)
 2 files changed, 83 insertions(+), 2 deletions(-)
```

- `engine/signal_engine.py`: parameter `suppress_dispatch` di `process_signal()` + satu blok `if suppress_dispatch: ... return True` sebelum `safe_dispatch()`. Tidak ada perubahan pada dedup/risk/macro-gateway yang sudah ada.
- `interfaces/telegram_bot.py`: import `check_drawdown` (try/except, opsional); fungsi baru `_notify_drawdown_breaker_transition()` + 2 konstanta pesan; pemanggilan fungsi itu di `snapshot_job()`; `_dispatch_and_record_deterministic_signal()` diperluas dengan cek breaker + `dispatch_status` bersyarat.
- **Tidak disentuh sama sekali**: `engine/portfolio/drawdown_protector.py`, `engine/shadow/e3_shadow.py`, `.env`, dan seluruh logika strategi trading (`engine/brain/`, `engine/strategy/`).

---

## Hasil Test

### Test baru (`tests/test_drawdown_broadcast_gate.py`) — 11/11 PASSED

```
TestProcessSignalSuppressDispatch::test_suppress_dispatch_skips_safe_dispatch_but_returns_true PASSED
TestProcessSignalSuppressDispatch::test_normal_dispatch_still_calls_safe_dispatch PASSED
TestDeterministicDispatchSuppression::test_three_live_losses_suppresses_dispatch_but_still_records PASSED
TestDeterministicDispatchSuppression::test_no_losses_dispatches_normally PASSED
TestDeterministicDispatchSuppression::test_two_losses_does_not_suppress PASSED
TestBreakerTransitionNotifications::test_no_transition_when_never_active PASSED
TestBreakerTransitionNotifications::test_activation_sends_exactly_one_warning_and_no_repeat PASSED
TestBreakerTransitionNotifications::test_reset_sends_exactly_one_confirmation_and_resumes_dispatch PASSED
TestBreakerTransitionNotifications::test_state_persists_across_simulated_restart PASSED
TestShadowAndLlmUnaffectedByBreaker::test_llm_source_signal_dispatches_via_process_signal_unaffected_by_breaker PASSED
TestShadowAndLlmUnaffectedByBreaker::test_shadow_e3_dispatch_ignores_breaker_state PASSED

11 passed in 22.93s
```

Mencakup keenam item wajib prompt:
1. 3 LOSS beruntun → sinyal ke-4 tetap masuk `signal_tracking` (`dispatch_status='SUPPRESSED'`, `status='OPEN'`), `safe_dispatch` **tidak** dipanggil.
2. Transisi aktivasi: tepat 1 pesan peringatan; siklus berikutnya tanpa WIN baru → 0 pesan tambahan.
3. WIN menutup streak → tepat 1 pesan reset, dan `[TRADE SIGNAL]` berikutnya kembali ter-dispatch normal (`dispatch_mock.assert_called_once()`).
4. `shadow_e3` (test eksplisit lewat `_run_shadow_e3`) dan `llm` (test eksplisit lewat `process_signal()` langsung) **tetap dispatch normal** walau breaker deterministic aktif.
5. State tahan restart: `ngov._state_cache = None` (simulasi restart — cache in-memory dibuang, baca ulang dari `STATE_FILE` di disk) → tidak kirim ulang pesan aktivasi yang sama.
6. Regresi.

### Regresi — full test scope

```
venv/bin/python -m pytest tests/ test_telegram_authorization.py test_dashboard_*.py -q
245 passed, 3 warnings, 74 subtests passed in 29.53s
```
(234 sebelumnya + 11 test baru = 245, tidak ada yang gagal.)

---

## Contoh Konkret Notifikasi Transisi (Before/After)

**SEBELUM** (perilaku `main` sebelum branch ini): apa pun jumlah LOSS beruntun pada `signal_tracking` (`source='deterministic'`), `[TRADE SIGNAL]` tetap dikirim ke Telegram setiap kali TradingBrain mendeteksi setup baru yang lolos RR≥3/confidence≥70 — `check_drawdown()` memang sudah membaca data live (`db0d4e0`), tapi hasilnya tidak pernah dikonsultasikan di jalur broadcast, hanya di `/entry`.

**SESUDAH** (branch ini), diverifikasi lewat test `test_activation_sends_exactly_one_warning_and_no_repeat` dan `test_reset_sends_exactly_one_confirmation_and_resumes_dispatch`:

Saat 3 LOSS live berturut untuk `deterministic` (mis. BTC, ETH, SOL semua LOSS) — siklus `snapshot_job` berikutnya (dalam ~60 detik) mengirim **tepat satu kali**:
```
⚠️ Circuit breaker aktif — 3 sinyal produksi beruntun rugi. Pengiriman sinyal
[TRADE SIGNAL] dijeda sampai ada sinyal yang profit lagi. (Ini bukan berarti
trading dihentikan permanen — cuma jeda otomatis untuk mencegah kerugian
beruntun.)
```
Selama itu, kalau TradingBrain tetap mendeteksi setup baru (mis. ARB OVERSOLD BOUNCE), sinyal itu **tetap masuk ke `/signal_stats`/`get_signal_stats()`** (baris `dispatch_status='SUPPRESSED'`, `status='OPEN'` sampai `signal_check_job` menutupnya) tapi **tidak muncul di chat Telegram user sama sekali** — log server mencatat:
```
[TRADE SIGNAL] SUPPRESSED — drawdown breaker active, loss_streak=3 coin=ARB setup=OVERSOLD BOUNCE
```
Siklus-siklus snapshot berikutnya (setiap ~60 detik) selama breaker tetap aktif **tidak** mengirim ulang pesan peringatan itu (state `drawdown_breaker.active=True` sudah tersimpan di `data/alert_cooldown_state.json`).

Begitu ada WIN baru yang menutup streak (mis. XRP WIN), siklus berikutnya mengirim **tepat satu kali**:
```
✅ Circuit breaker nonaktif — sinyal [TRADE SIGNAL] kembali dikirim normal.
```
dan sinyal `[TRADE SIGNAL]` berikutnya (mis. ADA) kembali ter-dispatch ke Telegram seperti biasa.

---

## Yang SENGAJA TIDAK Dikerjakan (sesuai instruksi)

- **Tidak merge/deploy** — semua perubahan ada di branch `feat/drawdown-gate-broadcast`, tidak ada commit yang dibuat, tidak ada restart service.
- `check_drawdown()`/`LOSS_STREAK_THRESHOLD` tidak diubah.
- `/entry` tidak diubah.
- `shadow_e3`/`llm`/evening-morning-summary tidak disentuh — dibuktikan lewat grep (`suppress_dispatch` cuma 1 call site) dan test eksplisit (kedua test di `TestShadowAndLlmUnaffectedByBreaker`).
- `.env` produksi tidak disentuh — tidak ada env var baru yang dibutuhkan fitur ini (pesan dan ambang breaker hardcoded string/reuse `LOSS_STREAK_THRESHOLD` yang sudah ada).

## Rekomendasi Sebelum Merge

1. Review pesan notifikasi (bahasa/nada) — teks saat ini mengikuti persis draft di prompt, bisa disesuaikan.
2. Pertimbangkan apakah `dispatch_status='SUPPRESSED'` perlu tampil di `/signal_stats` (saat ini tidak dibedakan di ringkasan — breakdown `by_source`/`by_setup` tetap menghitungnya sebagai bagian dari `deterministic`, hanya kolom mentah `dispatch_status` di DB yang membedakan). Kalau user ingin visibilitas eksplisit ("N sinyal ditekan breaker minggu ini"), itu perlu perubahan tambahan di luar scope prompt ini.
3. Setelah merge, disarankan pantau log `[TRADE SIGNAL] SUPPRESSED` dan pesan transisi selama beberapa siklus loss-streak pertama di produksi untuk memastikan perilaku sesuai ekspektasi sebelum dianggap final.
