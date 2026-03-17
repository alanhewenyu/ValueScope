# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Shared utility functions for the backend."""

from modeling.constants import TERMINAL_RISK_PREMIUM


def _build_valuation_params(raw_params, base_year, risk_free_rate, _is_ttm, _ttm_quarter, _ttm_label,
                            forecast_year_1=None, fy_end_month=12):
    """Build the full valuation_params dict from raw parameter values."""
    return {
        'base_year': base_year,
        'forecast_year_1': forecast_year_1 if forecast_year_1 is not None else base_year + 1,
        'fy_end_month': fy_end_month,
        'ttm_quarter': _ttm_quarter if _is_ttm else '',
        'ttm_label': _ttm_label if _is_ttm else '',
        'revenue_growth_1': raw_params['revenue_growth_1'],
        'revenue_growth_2': raw_params['revenue_growth_2'],
        'ebit_margin': raw_params['ebit_margin'],
        'convergence': raw_params['convergence'],
        'revenue_invested_capital_ratio_1': raw_params['revenue_invested_capital_ratio_1'],
        'revenue_invested_capital_ratio_2': raw_params['revenue_invested_capital_ratio_2'],
        'revenue_invested_capital_ratio_3': raw_params['revenue_invested_capital_ratio_3'],
        'tax_rate': raw_params['tax_rate'],
        'wacc': raw_params['wacc'],
        'terminal_wacc': risk_free_rate + TERMINAL_RISK_PREMIUM,
        'ronic': raw_params['ronic'],
        'risk_free_rate': risk_free_rate,
    }
