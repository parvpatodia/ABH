import json
import os
import random
from typing import Any, Dict, List, Optional

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "catalog.json")

LATENCY_SCORE = {"fast": 3.0, "medium": 2.0, "slow": 1.0}


def load_catalog() -> List[Dict[str, Any]]:
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("items", [])


def market_multiplier(provider: str) -> float:
    base = {
        "openai": 1.0,
        "replicate": 1.0,
        "aws": 1.0,
        "databricks": 1.0,
        "apify": 1.0,
        "requests": 1.0
    }
    m = base.get(provider, 1.0)
    jitter = random.uniform(0.98, 1.02)
    return m * jitter


def effective_price(item: Dict[str, Any], task_type: str, state_tokens: int) -> float:
    price = float(item.get("price", 999999.0))
    unit = str(item.get("price_unit", ""))

    if unit == "per_1k_tokens_usd":
        tokens_used = 1200 if task_type == "text_generation" else 0
        price = price * (tokens_used / 1000.0)

    provider = str(item.get("provider"))
    return round(price * market_multiplier(provider), 6)


def switching_cost(current_provider: Optional[str], candidate_provider: str, state_tokens: int, unit: str, unit_price: float) -> float:
    if not current_provider or current_provider == candidate_provider:
        return 0.0

    migration = 0.0
    if unit == "per_1k_tokens_usd":
        migration = (state_tokens / 1000.0) * unit_price

    validation = 0.0005
    return round(migration + validation, 6)


def risk_penalty(reliability: float) -> float:
    failure_prob = max(0.0, 1.0 - float(reliability))
    return round(failure_prob * 0.01, 6)


def base_score(objective: str, quality: float, latency: str, price: float) -> float:
    ls = LATENCY_SCORE.get(latency, 2.0)

    if objective == "cost":
        return -price
    if objective == "quality":
        return quality
    if objective == "speed":
        return ls
    if objective == "balanced":
        return (quality * 1.0) + (ls * 0.5) - (price * 50.0)

    return -price


def route_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    task_type = payload.get("task_type", "text_generation")
    budget = float(payload.get("budget_usd", 0.1))
    objective = payload.get("objective", "balanced")
    current_provider = payload.get("current_provider")
    state_tokens = int(payload.get("state_tokens", 1200))

    catalog = load_catalog()
    candidates = [c for c in catalog if task_type in c.get("task_types", [])]

    enriched = []
    for c in candidates:
        c2 = dict(c)
        c2["effective_price"] = effective_price(c2, task_type, state_tokens)
        enriched.append(c2)

    feasible = [c for c in enriched if float(c.get("effective_price", 999999.0)) <= budget]
    pool = feasible if feasible else enriched

    scored = []
    for c in pool:
        provider = str(c.get("provider"))
        name = str(c.get("name"))
        unit = str(c.get("price_unit", ""))
        price_eff = float(c.get("effective_price"))
        quality = float(c.get("quality", 0.0))
        latency = str(c.get("latency", "medium"))
        reliability = float(c.get("reliability", 0.95))

        base = base_score(objective, quality, latency, price_eff)
        sw = switching_cost(current_provider, provider, state_tokens, unit, price_eff)
        risk = risk_penalty(reliability)
        total = base - (sw * 30.0) - (risk * 30.0)

        scored.append((c, total, base, sw, risk))

    scored.sort(key=lambda x: x[1], reverse=True)

    best, total, base, sw, risk = scored[0]

    ranked = []
    for c, total, base, sw, risk in scored[:5]:
        ranked.append({
            "provider": c.get("provider"),
            "name": c.get("name"),
            "price_unit": c.get("price_unit"),
            "effective_price": c.get("effective_price"),
            "latency": c.get("latency"),
            "quality": c.get("quality"),
            "reliability": c.get("reliability"),
            "breakdown": {
                "base_score": round(base, 6),
                "switching_cost_usd": round(sw, 6),
                "risk_penalty_usd": round(risk, 6),
                "total_score": round(total, 6),
                "objective": objective,
                "current_provider": current_provider
            }
        })

    return {
        "ok": True,
        "task_type": task_type,
        "budget_usd": budget,
        "objective": objective,
        "note": None if feasible else "No option fits budget. Returning best available.",
        "recommendation": ranked[0],
        "top_options": ranked
    }