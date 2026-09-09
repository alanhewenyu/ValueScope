"""Phase 1 hands over analysis material — and no valuation.

A DCF mechanically extrapolated from 5Y averages is not a baseline, and a
number returned before the model reasons only anchors it. Phase 1 therefore
carries historical context, engine-computed WACC/tax and the analyst guide;
every price-bearing field belongs to phase 2.

Run: .venv/bin/python -m pytest backend/tests/ -q
"""
import pytest

from backend import mcp_server


@pytest.fixture
def payload(monkeypatch):
    monkeypatch.setattr(mcp_server, "_build_analysis_context", lambda t, k: {
        "guide": "GUIDE",
        "company_name": "Test Co",
        "market_price": 100.0,
        "currency": "CNY",
        "reported_currency": "CNY",
        "engine_computed": {"wacc_pct": 8.1, "average_tax_rate_pct": 25.0},
        "base_period": "2026",
        "ttm": "Q2 TTM (as of 2026-06-30)",
    })
    monkeypatch.setattr(mcp_server, "_track", lambda *a, **k: None)
    defaults = {
        "suggested": {"revenue_growth_1": 5.0},
        "history": {"revenue_growth": {"values": {"2024": 1.0, "2025": 3.0}}},
    }
    return mcp_server._analysis_payload("600519.SS", "", defaults, None, "1.2.3.4")


def test_phase_1_carries_no_valuation(payload):
    assert payload["phase"] == "context"
    for key in payload:
        assert "dcf" not in key.lower(), f"phase 1 must not carry {key}"
    assert "intrinsic_value_per_share" not in payload
    assert "bridge" not in payload
    # The market price is a fact about today, not a valuation — it stays.
    assert payload["company"]["market_price"] == 100.0


def test_phase_1_carries_the_analyst_material(payload):
    assert payload["parameter_analysis_guide"] == "GUIDE"
    assert payload["engine_computed"]["wacc_pct"] == 8.1
    assert payload["engine_computed"]["average_tax_rate_pct"] == 25.0
    assert payload["historical_defaults"] == {"revenue_growth_1": 5.0}
    # Ranges come with a sparkline so the model can see the shape at a glance.
    assert payload["parameter_history"]["revenue_growth"]["sparkline"]


def test_phase_1_frames_defaults_as_a_fallback_not_a_baseline(payload):
    assert "基线" not in payload["next_step"]
    assert "兜底" in payload["next_step"]
