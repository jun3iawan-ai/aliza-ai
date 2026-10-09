"""
Tests for the evening-summary / "KEPUTUSAN HARI INI" report bugs found in
EVENING_SUMMARY_AUDIT_FIX_REPORT.md:

- Target 1 ("ambil 50%", partial) must always be nearer to entry than
  Target 2 ("ambil sisa", final/RR-defining) — enforce_min_rr used to only
  rewrite "Target 1" to satisfy the 2.0x minimum RR without checking it
  against Target 2, which could push Target 1 past Target 2 for LONG setups
  (reproduced live for BTC/ETH/SOL/XRP on 2026-07-21's evening summary).
- The SL "(X% dari entry)" label must always match the Entry/SL actually
  shown in the same message, not whatever percentage the LLM wrote.
- A failed main-analysis parse must not leak internal wording ("LLM tidak
  mengikuti format") into the Telegram message.

Also covers the disclaimer added per EVENING_SUMMARY_AUDIT_FIX_REPORT.md's
follow-up: SARAN SPOT/FUTURES must always state explicitly that Entry/SL/
Target are AI (LLM) estimates, not backtested/winrate-validated signals —
appended in code (not relying on the LLM to write it itself) so it can never
be silently missing.

These are all pure-Python bugs/additions in `_reorder_section_by_rr` (a
deterministic post-processing layer over the LLM's free-text Entry/SL/Target/
RR numbers) — no LLM prompt behavior or trading logic is touched.
"""

import os
from unittest.mock import patch

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot as tb


def _long_entry(entry, sl, sl_label_pct, t1, t1_pct, t2, t2_pct, rr="1.0", spot=False):
    header = "  Entry ideal: $%s — tunggu harga ke sini\n  Entry sekarang: $%s LAYAK\n" % (entry, entry) if spot else "  Entry: $%s — konfirmasi dulu sebelum entry\n" % entry
    coin_line = "• BTC LONG\n" if spot else "• BTC: LONG\n"
    return (
        coin_line
        + header
        + f"  SL: ${sl} ({sl_label_pct}% dari entry)\n"
        + f"  Target 1: ${t1} ({t1_pct}%) — ambil 50%\n"
        + f"  Target 2: ${t2} ({t2_pct}%) — ambil sisa\n"
        + ("" if spot else "  Leverage: 3x\n")
        + f"  RR: {rr}x\n"
        + "  Invalidasi: Jika harga tutup di bawah $" + sl + "\n"
    )


import unittest


class TargetOrderTestCase(unittest.TestCase):
    def test_target1_forced_farther_than_target2_gets_swapped_back(self):
        """Reproduces the exact BTC bug from 2026-07-21: LLM's own Target 1 was
        near (RR < 2.0x) and got forced outward past Target 2 by the old
        enforce_min_rr. After the fix, Target 1 stays the nearer of the two."""
        section = _long_entry(
            entry="66,000.00", sl="62,040.00", sl_label_pct="5",
            t1="68,500.00", t1_pct="+3.8", t2="70,000.00", t2_pct="+6.1",
            rr="1.1",
        )
        out = tb._reorder_section_by_rr(section)
        import re
        t1_val = float(re.search(r"Target 1:\s*\$([\d,]+\.?\d*)", out).group(1).replace(",", ""))
        t2_val = float(re.search(r"Target 2:\s*\$([\d,]+\.?\d*)", out).group(1).replace(",", ""))
        entry_val = float(re.search(r"Entry:\s*\$([\d,]+\.?\d*)", out).group(1).replace(",", ""))
        self.assertLess(t1_val, t2_val, "Target 1 must be nearer to entry than Target 2 for a LONG")
        self.assertGreater(t1_val, entry_val)
        self.assertGreater(t2_val, entry_val)

    def test_fully_swapped_labels_get_corrected(self):
        """LLM wrote Target 1 as the far one and Target 2 as the near one —
        values must end up in the right slots regardless of the LLM's label.
        (Far target of 2,200 is only 2.0x RR here after the swap, right at
        MIN_RR — enforce_min_rr leaves it untouched.)"""
        section = _long_entry(
            entry="2,000.00", sl="1,900.00", sl_label_pct="5.0",
            t1="2,200.00", t1_pct="+10.0", t2="2,050.00", t2_pct="+2.5",
            rr="1.8",
        )
        out = tb._reorder_section_by_rr(section)
        import re
        t1_val = float(re.search(r"Target 1:\s*\$([\d,]+\.?\d*)", out).group(1).replace(",", ""))
        t2_val = float(re.search(r"Target 2:\s*\$([\d,]+\.?\d*)", out).group(1).replace(",", ""))
        self.assertEqual(t1_val, 2050.0)
        self.assertEqual(t2_val, 2200.0)

    def test_rr_is_still_computed_from_the_far_target(self):
        """RR must keep meaning 'R-multiple of the final/ambil-sisa target' —
        the fix only corrects which target gets which label, not what RR means."""
        section = _long_entry(
            entry="85.00", sl="80.75", sl_label_pct="5.0",
            t1="87.00", t1_pct="+2.4", t2="93.50", t2_pct="+10.0",
            rr="2.0",
        )
        out = tb._reorder_section_by_rr(section)
        self.assertIn("RR: 2.0x", out)

    def test_already_correct_ordering_is_left_unchanged_and_idempotent(self):
        section = _long_entry(
            entry="85.00", sl="80.75", sl_label_pct="5.0",
            t1="87.00", t1_pct="+2.4", t2="93.50", t2_pct="+10.0",
            rr="2.0",
        )
        out1 = tb._reorder_section_by_rr(section)
        out2 = tb._reorder_section_by_rr(out1)
        self.assertEqual(out1.strip(), out2.strip())

    def test_short_entry_target1_stays_nearer_than_target2(self):
        section = (
            "• BTC: SHORT\n"
            "  Entry: $66,000.00 — konfirmasi dulu sebelum entry\n"
            "  SL: $69,300.00 (5% dari entry)\n"
            "  Target 1: $64,000.00 (+3.0%) — ambil 50%\n"
            "  Target 2: $63,500.00 (+3.8%) — ambil sisa\n"
            "  Leverage: 3x\n"
            "  RR: 1.0x\n"
            "  Invalidasi: Jika harga tutup di atas $69300\n"
        )
        out = tb._reorder_section_by_rr(section)
        import re
        t1_val = float(re.search(r"Target 1:\s*\$([\d,]+\.?\d*)", out).group(1).replace(",", ""))
        t2_val = float(re.search(r"Target 2:\s*\$([\d,]+\.?\d*)", out).group(1).replace(",", ""))
        entry_val = 66000.0
        # For a SHORT, "nearer" means closer to entry from below in profit terms
        # i.e. Target 1 must be less far below entry than Target 2.
        self.assertLess(entry_val - t1_val, entry_val - t2_val)


class SlPercentageLabelTestCase(unittest.TestCase):
    def test_btc_mislabeled_5pct_corrected_to_actual_6pct(self):
        """Reproduces the exact BTC bug: SL $62,040 on Entry $66,000 is really
        6.00% away, but the LLM wrote '(5% dari entry)'."""
        section = _long_entry(
            entry="66,000.00", sl="62,040.00", sl_label_pct="5",
            t1="68,500.00", t1_pct="+3.8", t2="70,000.00", t2_pct="+6.1",
        )
        out = tb._reorder_section_by_rr(section)
        self.assertIn("SL: $62,040.00 (6.0% dari entry)", out)
        self.assertNotIn("(5% dari entry)", out)

    def test_xrp_mislabeled_4_5pct_corrected_to_actual_6_4pct(self):
        """Reproduces the exact XRP bug: SL $1.03 on Entry $1.10 is 6.36% away
        (rounds to 6.4%), but the LLM wrote '(4.5% dari entry)'."""
        section = (
            "• XRP: LONG\n"
            "  Entry: $1.10 — konfirmasi dulu sebelum entry\n"
            "  SL: $1.03 (4.5% dari entry)\n"
            "  Target 1: $1.15 (+4.5%) — ambil 50%\n"
            "  Target 2: $1.24 (+12.7%) — ambil sisa\n"
            "  Leverage: 3x\n"
            "  RR: 1.5x\n"
            "  Invalidasi: Jika harga tutup di bawah $1.03\n"
        )
        out = tb._reorder_section_by_rr(section)
        self.assertIn("(6.4% dari entry)", out)
        self.assertNotIn("(4.5% dari entry)", out)

    def test_already_correct_label_is_unaffected(self):
        section = _long_entry(
            entry="85.00", sl="80.75", sl_label_pct="5.0",
            t1="87.00", t1_pct="+2.4", t2="93.50", t2_pct="+10.0",
        )
        out = tb._reorder_section_by_rr(section)
        self.assertIn("(5.0% dari entry)", out)


_BRIEF_PATCHES = dict(
    _get_cross_asset_data={"dxy": None, "gold": None, "oil": None, "sp500": None, "vix": None},
    _fetch_crypto_news=[],
    _fetch_macro_news=[],
    _get_stablecoin_data={"interpretation": "-", "usdt_dominance": None},
    _get_deribit_options={"interpretation": "-", "put_call_ratio": None, "max_pain": None},
    _get_coinbase_premium={"interpretation": "-", "premium_pct": None},
    _get_institutional_data={
        "etf_flow_usd_m": None, "etf_flow_7d_usd_m": None,
        "etf_sentiment": "-", "netflow_btc": None, "netflow_sentiment": "-",
        "liq_above": None, "liq_below": None,
    },
    _build_coin_details_for_brief=({}, ""),
    _intraday_ranges_since_morning={"BTC": {"open": 1.0, "high": 2.0, "low": 0.5, "last": 1.5}},
)


def _brief_data():
    return {
        "market_score": 50, "market_label": "Neutral", "fear_greed": 50,
        "btc_dominance": 55.0, "top_coins": {}, "funding_rates": {}, "macro": {},
        "active_signal": None, "events_tomorrow": [], "context_summary": "",
    }


async def _run_brief(fake_llm, mode="pagi"):
    import contextlib
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(tb, "ask_aliza", object()))
        llm = stack.enter_context(patch.object(tb, "_call_llm_async", side_effect=fake_llm))
        for name, value in _BRIEF_PATCHES.items():
            stack.enter_context(patch.object(tb, name, return_value=value))
        out = await tb._generate_brief_analysis(_brief_data(), mode=mode)
    return out, llm


_GOOD_PAGI = """🧭 KONDISI HARI INI
Regime : RANGE
Bias   : Netral
Kejelasan: 5/10 — sinyal campur
Kenapa : funding panas, volume turun

🗺️ SKENARIO BTC
▲ Jika close 4H > 64.200 → 66.000
▬ Jika tetap di range → sideways
▼ Jika close 4H < 60.800 → 58.500

👀 COIN LAYAK DIPANTAU
• SOL — dekat support

⚠️ YANG HARUS DIHINDARI
• Leverage tinggi menjelang CPI

🚨 CATALYST
• 19:30 WIB — CPI AS"""


class FallbackMessageTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_does_not_leak_internal_implementation_wording(self):
        """LLM membalas format lama (SARAN SPOT) / rusak → fallback peta kondisi,
        tanpa kata-kata internal seperti 'LLM tidak mengikuti format'."""
        async def _contaminated(prompt):
            return "🟢 SARAN SPOT (Swing 1-7 hari)\nTidak ada setup spot yang layak."

        out, _ = await _run_brief(_contaminated)
        self.assertNotIn("LLM tidak mengikuti format", out)
        self.assertNotIn("Format analisis tidak sesuai", out)
        self.assertNotIn("SARAN SPOT", out)
        self.assertIn("🌅 PETA KONDISI", out)
        self.assertIn("🧭 KONDISI HARI INI", out)


class BriefMapFormatTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_pagi_single_llm_call_no_action_or_entry(self):
        async def _good(prompt):
            return _GOOD_PAGI

        out, llm = await _run_brief(_good)
        self.assertEqual(llm.await_count, 1)
        prompt = llm.await_args.args[0]
        self.assertIn("JANGAN memberi perintah beli/jual", prompt)
        self.assertTrue(out.startswith("🌅 PETA KONDISI — "))
        self.assertIn("🗺️ SKENARIO BTC", out)
        self.assertIn("bukan saran entry", out)
        for leak in ("Action:", "KEPUTUSAN HARI INI", "SARAN SPOT", "SARAN FUTURES"):
            self.assertNotIn(leak, out)

    async def test_duplicate_block_and_leaked_sections_are_dropped(self):
        leaky = _GOOD_PAGI + "\n\n🧭 KONDISI HARI INI\nRegime : TREND TURUN\n"
        leaky2 = _GOOD_PAGI.replace("🚨 CATALYST", "Action: 🟢 BELI\n🚨 CATALYST")

        async def _dup(prompt):
            return leaky
        out, _ = await _run_brief(_dup)
        self.assertEqual(out.count("🧭 KONDISI HARI INI"), 1)
        self.assertNotIn("TREND TURUN", out)

        async def _leak(prompt):
            return leaky2
        out2, _ = await _run_brief(_leak)
        self.assertNotIn("Action:", out2)
        self.assertNotIn("BELI", out2)

    async def test_malam_includes_morning_map_in_prompt(self):
        async def _good_malam(prompt):
            return ("🔄 APA YANG BERUBAH\nRegime : RANGE → RANGE\n\n📍 LEVEL YANG TERUJI\n• BTC 64.200 ❌\n\n"
                    "📊 SKENARIO YANG TERJADI\nSideways berjalan.\n\n🗺️ SKENARIO BESOK\n▲ Jika > 64.200\n\n"
                    "⚠️ PERHATIKAN BESOK\n• Weekend\n\n📅 EVENT BESOK\n• Tidak ada")

        state = {"text": "PETA-PAGI-PENANDA",
                 "levels": {"BTC": {"support": 0.8, "resistance": 1.8}}}
        with patch.object(tb, "_load_morning_state_today", return_value=state):
            out, llm = await _run_brief(_good_malam, mode="malam")
        prompt = llm.await_args.args[0]
        self.assertIn("PETA-PAGI-PENANDA", prompt)
        self.assertIn("high: 2.00 | low: 0.50", prompt)
        # section level dihitung kode, versi karangan LLM ("64.200") dibuang
        self.assertNotIn("• BTC 64.200 ❌", out)
        self.assertIn("BTC resistance 1.80 ❌ disentuh, gagal tembus (high 2.00)", out)
        self.assertIn("BTC support 0.80 ✅ disentuh, bertahan (low 0.50)", out)
        self.assertLess(out.index("📍 LEVEL YANG TERUJI"), out.index("📊 SKENARIO YANG TERJADI"))
        self.assertTrue(out.startswith("🌙 REVIEW HARI INI — "))
        self.assertIn("📍 LEVEL YANG TERUJI", out)


class LevelTestLinesTestCase(unittest.TestCase):
    def test_untouched_levels_are_excluded_and_breaks_detected(self):
        levels = {
            "BTC": {"support": 81037.99, "resistance": 86242.01},   # tidak tersentuh
            "ETH": {"support": 2400.0, "resistance": 2500.0},       # resistance tembus
            "SOL": {"support": 109.0, "resistance": 125.0},         # support jebol
        }
        ranges = {
            "BTC": {"open": 81808, "high": 82617.23, "low": 81603.52, "last": 82453.77},
            "ETH": {"open": 2478, "high": 2520, "low": 2471, "last": 2510},
            "SOL": {"open": 109.3, "high": 110.9, "low": 107.5, "last": 108.2},
        }
        lines = tb._level_test_lines(levels, ranges)
        joined = "\n".join(lines)
        self.assertNotIn("BTC", joined)
        self.assertIn("ETH resistance 2,500.00 ⚡ tembus", joined)
        self.assertIn("SOL support 109.00 ⚡ jebol", joined)
        self.assertEqual(len(lines), 2)


class BriefMapPersistenceTestCase(unittest.TestCase):
    def test_save_then_load_same_day_and_stale_day_ignored(self):
        import json, os, tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "brief_map_state.json")
            with patch.object(tb, "_BRIEF_MAP_STATE_PATH", path):
                tb._save_morning_map("isi peta pagi", levels={"BTC": {"support": 1.0}})
                self.assertEqual(tb._load_morning_map_today(), "isi peta pagi")
                self.assertEqual(tb._load_morning_state_today()["levels"], {"BTC": {"support": 1.0}})
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump({"date_wib": "2000-01-01", "text": "basi"}, fh)
                self.assertEqual(tb._load_morning_map_today(), "")


_AI_ESTIMATE_MARKERS = ("estimasi AI", "belum tervalidasi", "bukan sinyal yang sudah melalui backtest")


def _has_ai_estimate_disclaimer(text: str) -> bool:
    return any(marker.lower() in text.lower() for marker in _AI_ESTIMATE_MARKERS)


class AiEstimateDisclaimerTestCase(unittest.TestCase):
    """User decided (2026-07-21 follow-up): keep SARAN SPOT/FUTURES on the LLM +
    guardrail path as-is, but make it explicit to the user that Entry/SL/Target
    are AI estimates, not backtested/winrate-validated signals — unlike
    TradingBrain/E3 shadow. Must appear every time, not conditionally on
    whether the LLM happened to write something similar itself."""

    def test_futures_with_llm_risk_line_gets_disclaimer_merged_in(self):
        section = (
            "• BTC: LONG\n"
            "  Entry: $66,000.00 — konfirmasi dulu sebelum entry\n"
            "  SL: $62,040.00 (5% dari entry)\n"
            "  Target 1: $68,500.00 (+3.8%) — ambil 50%\n"
            "  Target 2: $70,000.00 (+6.1%) — ambil sisa\n"
            "  Leverage: 3x\n"
            "  RR: 1.1x\n"
            "  Invalidasi: Jika harga tutup di bawah $62000\n\n"
            "⚠️ Futures berisiko tinggi. Gunakan leverage rendah dan selalu pasang SL.\n"
        )
        out = tb._reorder_section_by_rr(section)
        self.assertTrue(_has_ai_estimate_disclaimer(out))
        # merged into the existing risk line, not duplicated as a brand new one
        self.assertEqual(out.count("Futures berisiko tinggi"), 1)

    def test_futures_without_llm_risk_line_still_gets_disclaimer(self):
        """LLM forgot to include its own risk-warning line entirely — the AI
        estimate disclaimer must still appear, since it's added in code."""
        section = (
            "• ETH: SHORT\n"
            "  Entry: $2,000.00 — konfirmasi dulu sebelum entry\n"
            "  SL: $2,100.00 (5% dari entry)\n"
            "  Target 1: $1,950.00 (+2.5%) — ambil 50%\n"
            "  Target 2: $1,800.00 (+10.0%) — ambil sisa\n"
            "  Leverage: 3x\n"
            "  RR: 1.0x\n"
            "  Invalidasi: Jika harga tutup di atas $2100\n"
        )
        out = tb._reorder_section_by_rr(section)
        self.assertTrue(_has_ai_estimate_disclaimer(out))

    def test_spot_section_gets_disclaimer_appended(self):
        """SARAN SPOT has no equivalent per-section risk line in the prompt
        template at all — the disclaimer must still be added fresh."""
        section = (
            "🟢 SARAN SPOT (Swing 1-7 hari)\n\n"
            "• BTC LONG\n"
            "  Entry ideal: $64,000.00 — tunggu harga ke sini\n"
            "  Entry sekarang: $66,000.00 KURANG IDEAL\n"
            "  SL: $62,040.00 (5% dari entry)\n"
            "  Target 1: $68,500.00 (+3.8%) — ambil 50%\n"
            "  Target 2: $70,000.00 (+6.1%) — ambil sisa\n"
            "  RR: 1.1x\n"
            "  Timeframe: 3-5 hari\n"
            "  Invalidasi: Jika harga tutup di bawah $62000\n"
        )
        out = tb._reorder_section_by_rr(section, is_spot=True)
        self.assertTrue(_has_ai_estimate_disclaimer(out))

    def test_no_setup_case_still_gets_disclaimer(self):
        """Disclaimer must not be conditional on there being an actual setup —
        it's about the section as a whole, not just entries with numbers."""
        section = (
            "📊 SARAN FUTURES (Swing 1-7 hari)\n"
            "Kondisi tidak mendukung futures saat ini.\n\n"
            "⚠️ Futures berisiko tinggi. Gunakan leverage rendah dan selalu pasang SL."
        )
        out = tb._reorder_section_by_rr(section)
        self.assertTrue(_has_ai_estimate_disclaimer(out))

    def test_disclaimer_is_not_duplicated_if_already_present(self):
        section = (
            "• BTC: LONG\n"
            "  Entry: $66,000.00 — konfirmasi dulu sebelum entry\n"
            "  SL: $62,040.00 (5% dari entry)\n"
            "  Target 1: $68,500.00 (+3.8%) — ambil 50%\n"
            "  Target 2: $70,000.00 (+6.1%) — ambil sisa\n"
            "  Leverage: 3x\n"
            "  RR: 1.1x\n"
            "  Invalidasi: Jika harga tutup di bawah $62000\n\n"
            "⚠️ Futures berisiko tinggi. Gunakan leverage rendah dan selalu pasang SL.\n"
        )
        out1 = tb._reorder_section_by_rr(section)
        out2 = tb._reorder_section_by_rr(out1)
        self.assertEqual(out1.count("estimasi AI"), 1)
        self.assertEqual(out2.count("estimasi AI"), 1)




class SpotAnalysisHeaderSafeguardTestCase(unittest.IsolatedAsyncioTestCase):
    """Regression for EVENING_SUMMARY_DUPLIKASI_AUDIT_REPORT.md poin 3: the
    "tidak ada setup" instruction in _generate_spot_analysis's prompt didn't
    repeat the "🟢 SARAN SPOT" header (unlike the equivalent instruction in
    _generate_futures_analysis, which does) — the LLM sometimes obeyed the
    literal "Tulis: <sentence>" instruction and dropped the header entirely,
    while _reorder_section_by_rr's unconditional AI-estimate disclaimer still
    got appended, producing a header-less section with a trailing disclaimer.
    This tests the programmatic safeguard in _generate_spot_analysis itself
    (prepend the header if the LLM's non-empty output omits it), independent
    of whether the prompt wording happens to be followed."""

    _CROSS_BUNDLE = {
        "sp500_str": "-", "vix_str": "-", "gold_str": "-", "oil_str": "-", "dxy_str": "-",
    }

    @staticmethod
    def _brief_data(score, fg):
        return {
            "market_score": score,
            "market_label": "Bearish" if score < 40 else "Bullish",
            "fear_greed": fg,
            "btc_dominance": 55.0,
            "funding_rates": {},
            "macro": {},
            "active_signal": None,
            "events_tomorrow": [],
            "context_summary": "",
        }

    async def test_missing_header_from_llm_gets_prepended(self):
        async def _headerless_llm(_prompt):
            # Simulates the LLM literally following "Tulis: <sentence>" and
            # omitting the "🟢 SARAN SPOT (Swing 1-7 hari)" header entirely —
            # exactly what triggered the header being missing from the
            # 2026-08-31 13:23 WIB "Ringkasan Malam" message.
            return "Tidak ada setup spot yang layak — tunggu pullback ke support."

        with patch.object(tb, "ask_aliza", object()), \
             patch.object(tb, "_call_llm_async", side_effect=_headerless_llm):
            out = await tb._generate_spot_analysis(
                self._brief_data(20, 15), {}, _cross_bundle=self._CROSS_BUNDLE
            )

        self.assertTrue(out.startswith("🟢 SARAN SPOT (Swing 1-7 hari)"))
        self.assertIn("Tidak ada setup spot yang layak", out)

    async def test_header_already_present_is_not_duplicated(self):
        well_formed = (
            "🟢 SARAN SPOT (Swing 1-7 hari)\n"
            "• BTC LONG\n"
            "  Entry ideal: $100 — tunggu harga ke sini\n"
        )

        async def _well_formed_llm(_prompt):
            return well_formed

        with patch.object(tb, "ask_aliza", object()), \
             patch.object(tb, "_call_llm_async", side_effect=_well_formed_llm):
            out = await tb._generate_spot_analysis(
                self._brief_data(70, 60), {}, _cross_bundle=self._CROSS_BUNDLE
            )

        self.assertEqual(out.count("🟢 SARAN SPOT"), 1)


class ParseAndRecordSignalsIdempotencyTestCase(unittest.TestCase):
    """Residual-risk guard from EVENING_SUMMARY_DUPLIKASI_AUDIT_REPORT.md
    poin 4: the 2026-08-31 duplication incident didn't corrupt
    signal_tracking only because the market was in the "TAHAN"/no-setup
    branch (no bullet coin entries to parse). If the KEPUTUSAN HARI INI
    duplication bug (poin 2) recurs while the market DOES have a valid
    bullet-point setup, _parse_and_record_signals must not write the same
    (coin, setup, entry, sl, tp) combination to signal_tracking twice."""

    def test_duplicated_identical_coin_block_is_recorded_once(self):
        duplicated_text = (
            "🟢 SARAN SPOT (Swing 1-7 hari)\n\n"
            "• BTC LONG\n"
            "  Entry ideal: $66,000.00 — tunggu harga ke sini\n"
            "  SL: $62,040.00 (6.0% dari entry)\n"
            "  Target 1: $68,500.00 (+3.8%) — ambil 50%\n"
            "  RR: 1.1x\n\n"
            "• BTC LONG\n"
            "  Entry ideal: $66,000.00 — tunggu harga ke sini\n"
            "  SL: $62,040.00 (6.0% dari entry)\n"
            "  Target 1: $68,500.00 (+3.8%) — ambil 50%\n"
            "  RR: 1.1x\n"
        )

        with patch.object(tb, "record_signal") as mock_record, \
             patch.object(tb, "get_market_snapshot", return_value={"market_intelligence": {"market_regime": "TRENDING"}}):
            tb._parse_and_record_signals(duplicated_text, market_score=50)

        self.assertEqual(mock_record.call_count, 1)

    def test_distinct_coin_blocks_are_all_recorded(self):
        text = (
            "🟢 SARAN SPOT (Swing 1-7 hari)\n\n"
            "• BTC LONG\n"
            "  Entry ideal: $66,000.00 — tunggu harga ke sini\n"
            "  SL: $62,040.00 (6.0% dari entry)\n"
            "  Target 1: $68,500.00 (+3.8%) — ambil 50%\n"
            "  RR: 1.1x\n\n"
            "• ETH LONG\n"
            "  Entry ideal: $2,400.00 — tunggu harga ke sini\n"
            "  SL: $2,256.00 (6.0% dari entry)\n"
            "  Target 1: $2,500.00 (+4.2%) — ambil 50%\n"
            "  RR: 1.2x\n"
        )

        with patch.object(tb, "record_signal") as mock_record, \
             patch.object(tb, "get_market_snapshot", return_value={"market_intelligence": {"market_regime": "TRENDING"}}):
            tb._parse_and_record_signals(text, market_score=50)

        self.assertEqual(mock_record.call_count, 2)
