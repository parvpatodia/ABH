"""
FastAPI server wrapping the Strands agent for local development.

Thin HTTP wrapper around the Strands agent. Payment protection is handled
entirely by @requires_payment on the tools — no FastAPI middleware needed.

Usage:
    poetry run agent
"""

import base64
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from strands.models.openai import OpenAIModel

from payments_py.x402.strands import extract_payment_required

from .analytics import analytics
from .pricing import PRICING_TIERS
from .strands_agent import NVM_PLAN_ID, create_agent

PORT = int(os.getenv("PORT", "3000"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

if not OPENAI_API_KEY:
    print("OPENAI_API_KEY is required. Set it in .env file.")
    sys.exit(1)

model = OpenAIModel(
    client_args={"api_key": OPENAI_API_KEY},
    model_id=os.getenv("MODEL_ID", "gpt-4o-mini"),
)
agent = create_agent(model)

app = FastAPI(
    title="Kit B - Data Selling Agent (Python)",
    description="Strands AI agent with x402 payment-protected data tools",
)


class DataRequest(BaseModel):
    query: str


@app.post("/data")
async def data(request: Request, body: DataRequest) -> JSONResponse:
    """Query data through the Strands agent.

    Payment is handled by @requires_payment on each tool. If no valid
    token is provided, the tool returns a PaymentRequired error which
    we translate into an HTTP 402 response with the standard headers.
    """
    try:
        payment_token = request.headers.get("payment-signature", "")
        state = {"payment_token": payment_token} if payment_token else {}

        result = agent(body.query, invocation_state=state)

        # Check if payment was required but not fulfilled
        payment_required = extract_payment_required(agent.messages)
        if payment_required and not state.get("payment_settlement"):
            encoded = base64.b64encode(
                json.dumps(payment_required).encode()
            ).decode()
            return JSONResponse(
                status_code=402,
                content={
                    "error": "Payment Required",
                    "message": str(result),
                },
                headers={"payment-required": encoded},
            )

        # Success — record analytics
        settlement = state.get("payment_settlement")
        credits = int(settlement.credits_redeemed) if settlement else 0
        analytics.record_request("request", credits)

        return JSONResponse(content={
            "response": str(result),
            "credits_used": credits,
        })

    except Exception as error:
        print(f"Error in /data: {error}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )


@app.get("/pricing")
async def pricing() -> JSONResponse:
    """Get pricing information (unprotected)."""
    return JSONResponse(content={
        "planId": NVM_PLAN_ID,
        "tiers": PRICING_TIERS,
    })


@app.get("/stats")
async def stats() -> JSONResponse:
    """Get usage statistics (unprotected)."""
    return JSONResponse(content=analytics.get_stats())


@app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint (unprotected)."""
    return JSONResponse(content={"status": "ok"})

@app.get("/", response_class=HTMLResponse)
async def home() -> HTMLResponse:
    html = """
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <title>TaskRoute AI</title>
      <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #0b1020; color: #e7e9ee; }
        .card { max-width: 820px; background: #111a33; border: 1px solid #243055; border-radius: 12px; padding: 20px; }
        h1 { margin: 0 0 8px 0; }
        .muted { color: #b7bfd6; }
        textarea, input, select { width: 100%; padding: 10px; border-radius: 10px; border: 1px solid #2b3a67; background: #0d1530; color: #e7e9ee; }
        button { padding: 10px 14px; border-radius: 10px; border: 0; background: #4c7dff; color: white; cursor: pointer; }
        button:hover { opacity: 0.9; }
        .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        pre { white-space: pre-wrap; background: #0d1530; border: 1px solid #2b3a67; padding: 12px; border-radius: 10px; }
        .pill { display: inline-block; padding: 6px 10px; background: #0d1530; border: 1px solid #2b3a67; border-radius: 999px; margin-right: 8px; }
      </style>
    </head>
    <body>
      <div class="card">
        <h1>TaskRoute AI</h1>
        <div class="muted">Paid routing decisions for agents. Returns a ranked plan across providers and models with effective price, switching cost estimate, and risk penalty.</div>

        <div style="margin-top: 14px;">
          <span class="pill">POST /data</span>
          <span class="pill">1 credit per call</span>
        </div>

        <h3 style="margin-top: 18px;">Try a request</h3>

        <div class="row">
          <div>
            <label>Task type</label>
            <select id="task_type">
              <option value="text_generation">text_generation</option>
              <option value="image_generation">image_generation</option>
              <option value="data_processing">data_processing</option>
            </select>
          </div>
          <div>
            <label>Objective</label>
            <select id="objective">
              <option value="cost">cost</option>
              <option value="speed">speed</option>
              <option value="quality">quality</option>
              <option value="balanced" selected>balanced</option>
            </select>
          </div>
        </div>

        <div class="row" style="margin-top: 12px;">
          <div>
            <label>Budget USD</label>
            <input id="budget_usd" value="0.1" />
          </div>
          <div>
            <label>State tokens</label>
            <input id="state_tokens" value="1200" />
          </div>
        </div>

        <div style="margin-top: 12px;">
          <label>Current provider (optional)</label>
          <input id="current_provider" placeholder="openai or replicate or aws" />
        </div>

        <div style="margin-top: 12px;">
          <button onclick="send()">Get Recommendation</button>
        </div>

        <h3 style="margin-top: 18px;">Response</h3>
        <pre id="out">Click Send to test. If you see 402 Payment Required, that is expected until a buyer agent settles payment.</pre>

        <p class="muted" style="margin-top: 14px;">
          Buyer agents should call /data with a JSON string in the query field. This UI is a convenience for humans.
        </p>
      </div>

      <script>
        async function send() {
          const task_type = document.getElementById("task_type").value;
          const objective = document.getElementById("objective").value;
          const budget_usd = parseFloat(document.getElementById("budget_usd").value);
          const state_tokens = parseInt(document.getElementById("state_tokens").value);
          const current_provider_raw = document.getElementById("current_provider").value.trim();
          const current_provider = current_provider_raw.length ? current_provider_raw : null;

          const payload = {
            task_type,
            objective,
            budget_usd,
            state_tokens,
            current_provider
          };

          const body = { query: JSON.stringify(payload) };

          const res = await fetch("/data", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
          });

          const text = await res.text();

          document.getElementById("out").textContent =
            "HTTP " + res.status + "\\n\\n" +
            "Response body:\\n" + text + "\\n\\n" +
            "Note: 402 is expected until a buyer pays via Nevermined.";
        }
      </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


def main():
    """Run the FastAPI server."""
    print(f"Data Selling Agent running on http://localhost:{PORT}")
    print("\nPayment protection via @requires_payment on Strands tools")
    print(f"Plan ID: {NVM_PLAN_ID}")
    print("\nEndpoints:")
    print("  POST /data     - Query data (send x402 token in 'payment-signature' header)")
    print("  GET  /pricing  - View pricing tiers")
    print("  GET  /stats    - View usage analytics")
    print("  GET  /health   - Health check")

    uvicorn.run(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
