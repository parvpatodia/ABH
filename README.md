# Nevermined AI Agent Examples

Examples of AI agents that use [Nevermined](https://nevermined.app) for payments. Each one shows a different way to gate access: x402 over HTTP, A2A, or MCP. You can run them locally with the commands below.

## What you need

- Python 3.10+
- [Poetry](https://python-poetry.org/) (or use pip and install deps from each agent’s `pyproject.toml`)
- A [Nevermined App](https://nevermined.app) account: you’ll need an API key and a payment plan (plan ID).
- An OpenAI API key for the LLM-backed agents.

## Env setup

Each agent lives in its own folder and expects a `.env` there. If the repo has a `.env.example`, copy it to `.env` and fill in values. Typical vars:

- `NVM_API_KEY` — from Nevermined App → API Keys (sandbox keys start with `sandbox:`, live with `live:`).
- `NVM_ENVIRONMENT` — `sandbox`, `staging_sandbox`, or `live`.
- `NVM_PLAN_ID` — from creating a pricing plan in Nevermined (credit-based, time-based, or trial).
- `OPENAI_API_KEY` — for any agent that calls an LLM.

## Agents

| Agent | What it does | Protocols |
|-------|----------------|-----------|
| **Buyer** | Finds sellers (A2A), buys data, respects budget | x402, A2A |
| **Seller** | Sells data / routing decisions; tiered pricing, 1 credit per call on paid tools | x402, A2A |
| **MCP Server** | Exposes payment-protected tools over MCP | MCP, x402 |
| **Strands** | Single Strands SDK agent with `@requires_payment` tools | x402 |

### Buyer (`agents/buyer-simple-agent/`)

Discovers sellers via A2A, pays for data, tracks spend. Has a React frontend.

```bash
cd agents/buyer-simple-agent
poetry install
poetry run python -m src.agent    # CLI, A2A
poetry run python -m src.web      # backend + React UI
```

### Seller (`agents/seller-simple-agent/`)

Sells a routing decision: given `task_type`, `budget_usd`, `objective`, and optional `current_provider` / `state_tokens`, it returns a ranked list of provider/model options with effective price, switching cost, and risk. Payment is 1 credit per request via x402.

- **POST /data** — Body: `{"query": "<json string>"}`. The JSON can be something like `{"task_type":"image_generation","budget_usd":0.1,"objective":"balanced"}`. Send a valid x402 token in the `payment-signature` header or you get **402 Payment Required** and a `payment-required` header (base64-encoded payload).
- **GET /pricing** — Plan ID and pricing tiers (no auth).
- **GET /stats** — Usage analytics (no auth).
- **GET /health** — Liveness.

The Strands tool `route_task` is wrapped with `@requires_payment`; settlement is handled by the payments SDK and we read `credits_redeemed` from the invocation state for stats.

```bash
cd agents/seller-simple-agent
poetry install
poetry run python -m src.agent      # HTTP server (x402)
poetry run python -m src.agent_a2a # A2A server
```

### MCP Server (`agents/mcp-server-agent/`)

MCP server with paid tools (e.g. search, summarize, research). Run `src.setup` once to register the agent and create a plan; then start the server.

```bash
cd agents/mcp-server-agent
poetry install
poetry run python -m src.setup
poetry run python -m src.server   # port 3000
```

### Strands (`agents/strands-simple-agent/`)

Strands agent with x402-protected tools and the full payment flow (402 → token → settlement).

```bash
cd agents/strands-simple-agent
poetry install
poetry run python agent.py
poetry run python demo.py
```

## Protocols (short version)

- **x402** — Payment over HTTP. Client sends `payment-signature` with an access token. If missing or invalid, server responds **402** and sets `payment-required` (base64 JSON). After payment, server returns 200 and the client can read settlement info (e.g. credits redeemed) from the response or from the SDK’s invocation state.
- **A2A** — Agent discovery via `/.well-known/agent.json`, JSON-RPC with payment extensions. Sellers can register with buyer marketplaces.
- **MCP** — Tools/plugins behind logical URLs; each tool can have its own credit cost.

## Docs in this repo

- [Getting Started](./docs/getting-started.md)
- [AWS Integration](./docs/aws-integration.md) — Strands + AgentCore
- [Deploy to AgentCore](./docs/deploy-to-agentcore.md)

## Links

- [Nevermined docs](https://nevermined.ai/docs)
- [Nevermined App](https://nevermined.app)
- [payments-py](https://github.com/nevermined-io/payments-py)
- [payments (TypeScript)](https://github.com/nevermined-io/payments)
- [x402 spec](https://github.com/coinbase/x402)
- [AWS AgentCore samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples)
- [Discord](https://discord.com/invite/GZju2qScKq)

License: MIT
