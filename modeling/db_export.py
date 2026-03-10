# Copyright (c) 2025 Alan He. Licensed under MIT.
"""Optional SQLite export for DCF valuation results.

Activated only when the VS_DB_PATH environment variable is set.
Usage:
    export VS_DB_PATH=/path/to/valuations.db
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
    """Save to DB if VS_DB_PATH is set. Silent no-op otherwise."""
    db_path = os.environ.get('VS_DB_PATH')
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
        print(f"[VS DB] Warning: failed to save to database: {e}", file=sys.stderr)
        return None


# ──────────────────────────────────────────────────────────────
# AI Usage Tracking (per-IP daily rate limiting)
# ──────────────────────────────────────────────────────────────

_AI_USAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_usage (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id  TEXT NOT NULL,
    used_at    TEXT NOT NULL DEFAULT (datetime('now')),
    ticker     TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_client_date ON ai_usage(client_id, used_at);
"""


def _ensure_ai_usage_table(db_path):
    """Create ai_usage table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    conn.executescript(_AI_USAGE_SCHEMA)
    conn.close()


def get_ai_usage_today(db_path, client_id):
    """Count today's AI calls for a given client_id."""
    try:
        _ensure_ai_usage_table(db_path)
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT COUNT(*) FROM ai_usage WHERE client_id = ? AND date(used_at) = date('now')",
            (client_id,),
        ).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


def get_ai_usage_stats(db_path):
    """Return today's AI usage grouped by client_id: list of (client_id, count, last_ticker)."""
    try:
        _ensure_ai_usage_table(db_path)
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT client_id, COUNT(*) as cnt, MAX(ticker) as last_ticker "
            "FROM ai_usage WHERE date(used_at) = date('now') "
            "GROUP BY client_id ORDER BY cnt DESC",
        ).fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def record_ai_usage(db_path, client_id, ticker=None):
    """Insert a new AI usage row."""
    try:
        _ensure_ai_usage_table(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO ai_usage (client_id, ticker) VALUES (?, ?)",
            (client_id, ticker),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[VS DB] Warning: failed to record AI usage: {e}", file=sys.stderr)


# ──────────────────────────────────────────────────────────────
# AI Quota Grants (per-IP extra quota from admin)
# ──────────────────────────────────────────────────────────────

_AI_GRANTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_quota_grants (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   TEXT NOT NULL,
    extra_quota INTEGER NOT NULL DEFAULT 0,
    grant_date  TEXT NOT NULL DEFAULT (date('now')),
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ai_grants_client_date ON ai_quota_grants(client_id, grant_date);
"""


def _ensure_ai_grants_table(db_path):
    """Create ai_quota_grants table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    conn.executescript(_AI_GRANTS_SCHEMA)
    conn.close()


def get_extra_quota_today(db_path, client_id):
    """Get total extra quota granted to a client (today's grants + permanent grants like invite codes)."""
    try:
        _ensure_ai_grants_table(db_path)
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT COALESCE(SUM(extra_quota), 0) FROM ai_quota_grants "
            "WHERE client_id = ? AND (grant_date = date('now') OR grant_date = '9999-12-31')",
            (client_id,),
        ).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


def grant_extra_quota(db_path, client_id, extra, note=None):
    """Grant extra AI quota to a specific client_id for today."""
    try:
        _ensure_ai_grants_table(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO ai_quota_grants (client_id, extra_quota, note) VALUES (?, ?, ?)",
            (client_id, extra, note),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[VS DB] Warning: failed to grant quota: {e}", file=sys.stderr)
        return False


def reset_usage_today(db_path, client_id):
    """Delete today's AI usage records for a specific client_id (reset quota)."""
    try:
        _ensure_ai_usage_table(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute(
            "DELETE FROM ai_usage WHERE client_id = ? AND date(used_at) = date('now')",
            (client_id,),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[VS DB] Warning: failed to reset usage: {e}", file=sys.stderr)
        return False


# ──────────────────────────────────────────────────────────────
# Invite Codes (redeemable quota vouchers)
# ──────────────────────────────────────────────────────────────

import secrets as _secrets
import string as _string

_INVITE_CODES_SCHEMA = """
CREATE TABLE IF NOT EXISTS invite_codes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT NOT NULL UNIQUE,
    quota        INTEGER NOT NULL DEFAULT 10,
    redeemed_by  TEXT,
    redeemed_at  TEXT,
    source       TEXT NOT NULL DEFAULT 'manual',
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_invite_code ON invite_codes(code);
"""


def _ensure_invite_codes_table(db_path):
    """Create invite_codes table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    conn.executescript(_INVITE_CODES_SCHEMA)
    conn.close()


def generate_invite_code(db_path, quota=10, source='manual', prefix='VIP'):
    """Generate a new invite code and store it in DB. Returns the code string."""
    try:
        _ensure_invite_codes_table(db_path)
        # Generate a short random code: VIP-XXXXXX (6 alphanumeric chars)
        suffix = ''.join(_secrets.choice(_string.ascii_lowercase + _string.digits) for _ in range(6))
        code = f"{prefix}-{suffix}"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO invite_codes (code, quota, source) VALUES (?, ?, ?)",
            (code, quota, source),
        )
        conn.commit()
        conn.close()
        return code
    except Exception as e:
        print(f"[VS DB] Warning: failed to generate invite code: {e}", file=sys.stderr)
        return None


def generate_invite_codes_batch(db_path, count=5, quota=10, source='manual', prefix='VIP'):
    """Generate multiple invite codes at once. Returns list of code strings."""
    codes = []
    for _ in range(count):
        code = generate_invite_code(db_path, quota=quota, source=source, prefix=prefix)
        if code:
            codes.append(code)
    return codes


def redeem_invite_code(db_path, code, client_id):
    """Redeem an invite code. Returns (success: bool, quota: int, error_key: str).

    error_key values: None (success), 'invalid', 'already_used'
    """
    try:
        # Ensure both tables exist before opening the working connection
        _ensure_invite_codes_table(db_path)
        _ensure_ai_grants_table(db_path)
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT id, quota, redeemed_by FROM invite_codes WHERE code = ?",
            (code.strip(),),
        ).fetchone()
        if not row:
            conn.close()
            return False, 0, 'invalid'
        _id, quota, redeemed_by = row
        if redeemed_by:
            conn.close()
            return False, 0, 'already_used'
        # Mark as redeemed + grant quota in one transaction
        conn.execute(
            "UPDATE invite_codes SET redeemed_by = ?, redeemed_at = datetime('now') WHERE id = ?",
            (client_id, _id),
        )
        conn.execute(
            "INSERT INTO ai_quota_grants (client_id, extra_quota, grant_date, note) "
            "VALUES (?, ?, '9999-12-31', ?)",
            (client_id, quota, f"invite:{code}"),
        )
        conn.commit()
        conn.close()
        return True, quota, None
    except Exception as e:
        print(f"[VS DB] Warning: failed to redeem invite code: {e}", file=sys.stderr)
        return False, 0, 'invalid'


def list_invite_codes(db_path, limit=50):
    """List invite codes (newest first). Returns list of dicts."""
    try:
        _ensure_invite_codes_table(db_path)
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT code, quota, redeemed_by, redeemed_at, source, created_at "
            "FROM invite_codes ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [
            {'code': r[0], 'quota': r[1], 'redeemed_by': r[2],
             'redeemed_at': r[3], 'source': r[4], 'created_at': r[5]}
            for r in rows
        ]
    except Exception:
        return []
