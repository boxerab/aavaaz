"""Shared SaaS plan definitions.

Single source of truth for the in-memory router (api/saas.py) and the Lambda
app (serverless/saas_lambda.py), which otherwise duplicated these tables and
drifted.
"""

import os

PRICE_PER_MINUTE = float(os.environ.get("AAVAAZ_PRICE_PER_MINUTE", "0.006"))

# Plans a user may buy through self-service checkout. Enterprise is sales-led.
PURCHASABLE_PLANS = {"pro"}

_INCLUDED_MINUTES = {"free": 60, "pro": 1000, "enterprise": 999999}
_PRICE_PER_MINUTE = {"free": 0.0, "pro": PRICE_PER_MINUTE, "enterprise": 0.004}


def included_minutes(plan: str) -> int:
    return _INCLUDED_MINUTES.get(plan, 60)


def price_per_minute(plan: str) -> float:
    return _PRICE_PER_MINUTE.get(plan, PRICE_PER_MINUTE)
