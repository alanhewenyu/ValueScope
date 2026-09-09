"""Numeric assumptions sent as strings must survive as numbers.

Models routinely send "2.0" instead of 2.0 (observed in a WorkBuddy run,
whose valuation matched the numeric call to the last decimal). Pydantic
coerces today. If that ever stopped, the MCP layer would reject the call —
or worse, the value would reach the engine as a string and be compared or
discounted as one. This pins the behaviour that keeps those runs correct.

Run: .venv/bin/python -m pytest backend/tests/ -q
"""
from backend.routers.valuation import DCFParams


ASSUMPTIONS = {
    "revenue_growth_1": 2.0,
    "revenue_growth_2": 4.0,
    "ebit_margin": 65.0,
    "convergence": 4,
    "revenue_invested_capital_ratio_1": 2.0,
    "revenue_invested_capital_ratio_2": 2.2,
    "revenue_invested_capital_ratio_3": 2.5,
    "tax_rate": 25.4,
    "wacc": 7.0,
}


def _params(as_string: bool) -> DCFParams:
    vals = {k: (str(v) if as_string else v) for k, v in ASSUMPTIONS.items()}
    return DCFParams(ticker="600519.SS", **vals)


def test_string_assumptions_match_the_numeric_call_field_by_field():
    numeric, stringy = _params(False), _params(True)
    for field in ASSUMPTIONS:
        assert getattr(stringy, field) == getattr(numeric, field), field


def test_coerced_assumptions_are_real_numbers():
    """A value left as str would compare and discount as text downstream."""
    stringy = _params(True)
    for field in ASSUMPTIONS:
        assert isinstance(getattr(stringy, field), float), field
