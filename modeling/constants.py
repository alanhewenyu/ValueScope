HISTORICAL_DATA_PERIODS_ANNUAL = 5  # 年度数据抓取 5 年

HISTORICAL_DATA_PERIODS_QUARTER = 12  # 季度数据抓取 8 个季度

MARGINAL_TAX_RATE = 0.25  # 25%

TERMINAL_RISK_PREMIUM = 0.05  # 5%

TERMINAL_RONIC_PREMIUM = 0.05

"""
Mature companies tend to have costs of INVESTED_CAPITAL closer to the market average. 
While the riskfree rate (e.g., 3-4%) is a close approximation of the average, you can use a slightly higher number (riskfree rate + 6%) for mature companies in riskier businesses and a slightly lower number (risfree rate + 4%) for safer companies
"""

RISK_FREE_RATE_US = 0.04  # 美国无风险利率 4%
RISK_FREE_RATE_CHINA = 0.03  # 中国无风险利率 2.5%
RISK_FREE_RATE_INTERNATIONAL = 0.03  # 其他国家无风险利率 3%