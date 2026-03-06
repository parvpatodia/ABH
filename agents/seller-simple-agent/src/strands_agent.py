"""
Strands agent definition with Nevermined x402 payment protected tools.

We sell a routing decision service that tells buyers which provider and model
to use given task type, budget, objective, and switching constraints.
"""

import json
import os
from typing import Any, Dict

import requests
from dotenv import load_dotenv
from strands import Agent, tool

from payments_py import Payments, PaymentOptions
from payments_py.x402.strands import requires_payment
from .taskroute_core import route_task as route_task_impl

load_dotenv()

NVM_API_KEY = os.environ["NVM_API_KEY"]
NVM_ENVIRONMENT = os.getenv("NVM_ENVIRONMENT", "sandbox")
NVM_PLAN_ID = os.environ["NVM_PLAN_ID"]
NVM_AGENT_ID = os.getenv("NVM_AGENT_ID")

TASKROUTE_URL = os.getenv("TASKROUTE_URL", "http://127.0.0.1:8000/optimize")

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key=NVM_API_KEY, environment=NVM_ENVIRONMENT)
)


def parse_request(query: str) -> Dict[str, Any]:
    """
    Buyers can send either JSON or a simple text query.
    If JSON parse fails, we fall back to a safe default.
    """

    try:
        data = json.loads(query)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    return {
        "task_type": "text_generation",
        "budget_usd": 0.05,
        "objective": "balanced",
        "current_provider": None,
        "state_tokens": 1200
    }


@tool(context=True)
@requires_payment(
    payments=payments,
    plan_id=NVM_PLAN_ID,
    credits=1,
    agent_id=NVM_AGENT_ID,
)
def route_task(query: str, tool_context=None) -> Dict[str, Any]:
    """
    Return a paid routing decision for an agent task. Costs 1 credit per request.

    Expected input format is JSON string:
    {
      "task_type": "image_generation",
      "budget_usd": 0.1,
      "objective": "balanced",
      "current_provider": null,
      "state_tokens": 1200
    }
    """

    payload = parse_request(query)

    r = requests.post(TASKROUTE_URL, json=payload, timeout=20)
    r.raise_for_status()
    #return r.json()
    return route_task_impl(payload)


SYSTEM_PROMPT = """\
You are a routing decision selling agent.

Your job is simple:
Take the user input, call route_task, and return the routing plan.

The routing plan tells the buyer which provider and model to use, including
cost, switching cost, and risk tradeoffs.

Always use the route_task tool for every request.
"""

TOOLS = [route_task]


def create_agent(model) -> Agent:
    return Agent(
        model=model,
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )