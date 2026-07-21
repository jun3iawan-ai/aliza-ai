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


class FallbackMessageTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_does_not_leak_internal_implementation_wording(self):
        """The rare (~1x/7 days observed live) path where the main analysis LLM
        call outputs SARAN SPOT/FUTURES/DISCLAIMER content instead of the 6
        required KEPUTUSAN HARI INI sections, leaving main_out empty after the
        dedup-truncation — must not expose phrases like 'LLM tidak mengikuti
        format' to the end user."""
        brief_data = {
            "market_score": 50,
            "market_label": "Neutral",
            "fear_greed": 50,
            "btc_dominance": 55.0,
            "top_coins": {},
            "funding_rates": {},
            "macro": {},
            "active_signal": None,
            "events_tomorrow": [],
            "context_summary": "",
        }

        async def _fake_llm_main_out_is_contaminated(prompt):
            # Simulates the LLM ignoring "Jangan tulis saran spot atau futures"
            # and answering with a SARAN SPOT block instead of the 6 sections.
            if "KEPUTUSAN HARI INI (WAJIB DIIKUTI)" in prompt and "6 section saja" in prompt:
                return "🟢 SARAN SPOT (Swing 1-7 hari)\nTidak ada setup spot yang layak."
            if "hanya saran spot" in prompt.lower():
                return "🟢 SARAN SPOT (Swing 1-7 hari)\nTidak ada setup spot yang layak — tunggu pullback ke support."
            return "📊 SARAN FUTURES (Swing 1-7 hari)\nKondisi tidak mendukung futures saat ini."

        with patch.object(tb, "ask_aliza", object()), \
             patch.object(tb, "_call_llm_async", side_effect=_fake_llm_main_out_is_contaminated), \
             patch.object(tb, "_get_cross_asset_data", return_value={"dxy": None, "gold": None, "oil": None, "sp500": None, "vix": None}), \
             patch.object(tb, "_fetch_crypto_news", return_value=[]), \
             patch.object(tb, "_fetch_macro_news", return_value=[]), \
             patch.object(tb, "_get_stablecoin_data", return_value={"interpretation": "-", "usdt_dominance": None}), \
             patch.object(tb, "_get_deribit_options", return_value={"interpretation": "-", "put_call_ratio": None, "max_pain": None}), \
             patch.object(tb, "_get_coinbase_premium", return_value={"interpretation": "-", "premium_pct": None}), \
             patch.object(tb, "_get_institutional_data", return_value={
                 "etf_flow_usd_m": None, "etf_flow_7d_usd_m": None,
                 "etf_sentiment": "-", "netflow_btc": None, "netflow_sentiment": "-",
                 "liq_above": None, "liq_below": None,
             }), \
             patch.object(tb, "_build_coin_details_for_brief", return_value=({}, "")):
            analysis = await tb._generate_brief_analysis(brief_data)

        self.assertNotIn("LLM tidak mengikuti format", analysis)
        self.assertNotIn("Format analisis tidak sesuai", analysis)
        self.assertIn("KEPUTUSAN HARI INI", analysis)


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
