"""The growth × margin table's axis labels match its rows and columns.

sensitivity_analysis puts Years 2-5 growth on the rows and EBIT margin on
the columns. The API used to label them the other way round, so anyone
reading the JSON (MCP clients reading the market-implied growth off the
table, the Excel export) read a transposed table.

Run: .venv/bin/python -m pytest backend/tests/ -q
"""
import pandas as pd

from backend.routers.valuation import _growth_margin_payload


def test_rows_are_growth_and_columns_are_margin():
    # value = growth * 100 + margin, so a transposed read is obvious
    growth, margin = [3.0, 8.0], [30.0, 35.0, 40.0]
    df = pd.DataFrame([[g * 100 + m for m in margin] for g in growth],
                      index=growth, columns=margin)
    payload = _growth_margin_payload(df)
    assert payload["growth_rates"] == growth
    assert payload["margins"] == margin
    g_i, m_j = payload["growth_rates"].index(8.0), payload["margins"].index(35.0)
    assert payload["table"][g_i][m_j] == 835.0
