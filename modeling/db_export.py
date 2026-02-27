# Copyright (c) 2025 Alan He. Licensed under MIT.
"""Optional SQLite export for DCF valuation results.

Activated only when the VALUX_DB_PATH environment variable is set.
Usage:
    export VALUX_DB_PATH=/path/to/valuations.db
"""

import json
import os
import sqlite3
import sys
from datetime import date

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS valuations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity
    ticker              TEXT NOT NULL,
    company_name        TEXT NOT NULL,
    valuation_date      TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),

    -- Mode
    mode                TEXT NOT NULL,
    ai_engine           TEXT,
    source              TEXT NOT NULL DEFAULT 'live',

    -- Company profile
    country             TEXT,
    exchange            TEXT,
    currency            TEXT,
    reported_currency   TEXT,
    beta                REAL,
    market_cap          REAL,
    market_price        REAL,
    outstanding_shares  REAL,

    -- Valuation parameters
    base_year           INTEGER,
    ttm_quarter         TEXT,
    ttm_label           TEXT,
    revenue_growth_1    REAL,
    revenue_growth_2    REAL,
    ebit_margin         REAL,
    convergence         REAL,
    rev_ic_ratio_1      REAL,
    rev_ic_ratio_2      REAL,
    rev_ic_ratio_3      REAL,
    tax_rate            REAL,
    wacc                REAL,
    terminal_wacc       REAL,
    ronic               REAL,
    risk_free_rate      REAL,

    -- DCF results
    pv_cf_10yr          REAL,
    pv_terminal         REAL,
    enterprise_value    REAL,
    equity_value        REAL,
    price_per_share     REAL,
    cash                REAL,
    total_investments   REAL,
    total_debt          REAL,
    minority_interest   REAL,

    -- Forex (stored at valuation time for historical accuracy)
    forex_rate          REAL,

    -- Gap analysis
    gap_dcf_price       REAL,
    gap_market_price    REAL,
    gap_pct             REAL,
    gap_adjusted_price  REAL,
    gap_adjusted_price_reporting REAL,
    gap_analysis_text   TEXT,

    -- AI data
    ai_raw_text         TEXT,
    ai_parameters_json  TEXT,

    -- Sensitivity data
    sensitivity_json    TEXT,
    wacc_sensitivity_json TEXT,
    wacc_base           REAL,

    -- Full data (JSON-serialized DataFrames)
    summary_json        TEXT,
    dcf_table_json      TEXT
);

-- Migration: add columns if they don't exist (for existing databases)
-- SQLite ignores errors on duplicate column adds via executescript,
-- so we use a safe approach in Python instead.

CREATE INDEX IF NOT EXISTS idx_ticker ON valuations(ticker);
CREATE INDEX IF NOT EXISTS idx_company_name ON valuations(company_name);
CREATE INDEX IF NOT EXISTS idx_valuation_date ON valuations(valuation_date);
CREATE INDEX IF NOT EXISTS idx_ticker_date ON valuations(ticker, valuation_date);
"""


def _migrate(conn):
    """Add new columns to existing databases (safe for fresh DBs too)."""
    existing = {r[1] for r in conn.execute("PRAGMA table_info(valuations)").fetchall()}
    for col, typ in [('summary_json', 'TEXT'), ('dcf_table_json', 'TEXT'),
                      ('gap_adjusted_price_reporting', 'REAL'),
                      ('forex_rate', 'REAL')]:
        if col not in existing:
            conn.execute(f"ALTER TABLE valuations ADD COLUMN {col} {typ}")
    # Migrate old 'ai' mode to 'copilot' (idempotent: no-op if no 'ai' rows)
    conn.execute("UPDATE valuations SET mode = 'copilot' WHERE mode = 'ai'")


def save_to_db(
    db_path,
    ticker,
    company_name,
    valuation_date,
    mode,
    ai_engine,
    valuation_params,
    results,
    company_profile,
    gap_analysis_result=None,
    ai_result=None,
    sensitivity_table=None,
    wacc_sensitivity=None,
    financial_data=None,
    source='live',
    forex_rate=None,
):
    """Insert one valuation record into SQLite. Returns the new row id."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA_SQL)
    _migrate(conn)

    # Serialize sensitivity DataFrame to JSON
    sens_json = None
    if sensitivity_table is not None:
        try:
            sens_dict = {}
            for idx in sensitivity_table.index:
                row_dict = {}
                for col in sensitivity_table.columns:
                    row_dict[str(col)] = float(sensitivity_table.loc[idx, col])
                sens_dict[str(idx)] = row_dict
            sens_json = json.dumps(sens_dict)
        except Exception:
            pass

    # Serialize WACC sensitivity
    wacc_sens_json = None
    wacc_base_val = None
    if wacc_sensitivity:
        wacc_results, wacc_base_val = wacc_sensitivity
        try:
            wacc_sens_json = json.dumps(
                {str(k): float(v) for k, v in wacc_results.items()}
            )
        except Exception:
            pass

    # Serialize AI parameters
    ai_params_json = None
    ai_raw = None
    if ai_result:
        ai_raw = ai_result.get('raw_text')
        params = ai_result.get('parameters')
        if params:
            try:
                ai_params_json = json.dumps(params, default=str, ensure_ascii=False)
            except Exception:
                pass

    # Serialize financial summary DataFrame
    summary_json = None
    if financial_data and 'summary' in financial_data:
        try:
            summary_json = financial_data['summary'].to_json(force_ascii=False)
        except Exception:
            pass

    # Serialize DCF forecast table
    dcf_table_json = None
    if results.get('dcf_table') is not None:
        try:
            dcf_table_json = results['dcf_table'].to_json(force_ascii=False)
        except Exception:
            pass

    gap = gap_analysis_result or {}

    cursor = conn.execute(
        """
        INSERT INTO valuations (
            ticker, company_name, valuation_date, mode, ai_engine, source,
            country, exchange, currency, reported_currency,
            beta, market_cap, market_price, outstanding_shares,
            base_year, ttm_quarter, ttm_label,
            revenue_growth_1, revenue_growth_2, ebit_margin, convergence,
            rev_ic_ratio_1, rev_ic_ratio_2, rev_ic_ratio_3,
            tax_rate, wacc, terminal_wacc, ronic, risk_free_rate,
            pv_cf_10yr, pv_terminal, enterprise_value, equity_value,
            price_per_share, cash, total_investments, total_debt,
            minority_interest,
            forex_rate,
            gap_dcf_price, gap_market_price, gap_pct, gap_adjusted_price,
            gap_adjusted_price_reporting, gap_analysis_text,
            ai_raw_text, ai_parameters_json,
            sensitivity_json, wacc_sensitivity_json, wacc_base,
            summary_json, dcf_table_json
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?,
            ?,
            ?, ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?
        )
        """,
        (
            ticker,
            company_name,
            valuation_date,
            mode,
            ai_engine,
            source,
            company_profile.get('country'),
            company_profile.get('exchange'),
            company_profile.get('currency'),
            results.get('reported_currency'),
            company_profile.get('beta'),
            company_profile.get('marketCap'),
            company_profile.get('price'),
            results.get('outstanding_shares'),
            valuation_params.get('base_year'),
            valuation_params.get('ttm_quarter', ''),
            valuation_params.get('ttm_label', ''),
            valuation_params.get('revenue_growth_1'),
            valuation_params.get('revenue_growth_2'),
            valuation_params.get('ebit_margin'),
            valuation_params.get('convergence'),
            valuation_params.get('revenue_invested_capital_ratio_1'),
            valuation_params.get('revenue_invested_capital_ratio_2'),
            valuation_params.get('revenue_invested_capital_ratio_3'),
            valuation_params.get('tax_rate'),
            valuation_params.get('wacc'),
            valuation_params.get('terminal_wacc'),
            valuation_params.get('ronic'),
            valuation_params.get('risk_free_rate'),
            results.get('pv_cf_next_10_years'),
            results.get('pv_terminal_value'),
            results.get('enterprise_value'),
            results.get('equity_value'),
            results.get('price_per_share'),
            results.get('cash'),
            results.get('total_investments'),
            results.get('total_debt'),
            results.get('minority_interest'),
            forex_rate,
            gap.get('dcf_price'),
            gap.get('current_price'),
            gap.get('gap_pct'),
            gap.get('adjusted_price'),
            gap.get('adjusted_price_reporting'),
            gap.get('analysis_text'),
            ai_raw,
            ai_params_json,
            sens_json,
            wacc_sens_json,
            wacc_base_val,
            summary_json,
            dcf_table_json,
        ),
    )

    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def update_gap_analysis(db_path, row_id, gap_analysis_result):
    """Update an existing row with gap analysis results."""
    if not db_path or not row_id or not gap_analysis_result:
        return
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            UPDATE valuations SET
                gap_dcf_price = ?,
                gap_market_price = ?,
                gap_pct = ?,
                gap_adjusted_price = ?,
                gap_adjusted_price_reporting = ?,
                gap_analysis_text = ?
            WHERE id = ?
            """,
            (
                gap_analysis_result.get('dcf_price'),
                gap_analysis_result.get('current_price'),
                gap_analysis_result.get('gap_pct'),
                gap_analysis_result.get('adjusted_price'),
                gap_analysis_result.get('adjusted_price_reporting'),
                gap_analysis_result.get('analysis_text'),
                row_id,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def maybe_save_to_db(
    ticker,
    company_name,
    mode,
    ai_engine,
    valuation_params,
    results,
    company_profile,
    gap_analysis_result=None,
    ai_result=None,
    sensitivity_table=None,
    wacc_sensitivity=None,
    financial_data=None,
    forex_rate=None,
):
    """Save to DB if VALUX_DB_PATH is set. Silent no-op otherwise."""
    db_path = os.environ.get('VALUX_DB_PATH')
    if not db_path:
        return None
    try:
        return save_to_db(
            db_path=db_path,
            ticker=ticker,
            company_name=company_name,
            valuation_date=date.today().isoformat(),
            mode=mode,
            ai_engine=ai_engine,
            valuation_params=valuation_params,
            results=results,
            company_profile=company_profile,
            gap_analysis_result=gap_analysis_result,
            ai_result=ai_result,
            sensitivity_table=sensitivity_table,
            wacc_sensitivity=wacc_sensitivity,
            financial_data=financial_data,
            forex_rate=forex_rate,
        )
    except Exception as e:
        print(f"[ValuX DB] Warning: failed to save to database: {e}", file=sys.stderr)
        return None
