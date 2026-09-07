# AI Customer Support & Sales Agent (WhatsApp)

A WhatsApp customer support agent for a fictional e-commerce brand (**AuraLoop
Electronics**) built around one non-negotiable rule: every fact the customer receives
about an order, refund, product, or ticket comes from a real tool call against real
data - never from the model's own memory.

## Architecture

```
WhatsApp -> Twilio Webhook -> Customer Identification (deterministic)
         -> Conversation Memory (last N messages + customer long-term fields)
         -> RAG (pgvector policy retrieval)
         -> AI Agent (LangGraph ReAct tool-calling loop, Gemini)
              -> tools: customer lookup, order lookup, product search,
                        ticket create/lookup, refund-eligibility check
         -> Decision Engine (deterministic Python - confidence / value /
              explicit-request / refund-ambiguity rules)
         -> Auto-Reply (Twilio send) OR Human Handoff (ticket + escalation, no
              agent draft sent)
```

**The one thing to understand about this codebase:** the LLM only ever does two
things - decide which tool(s) to call, and draft a reply. It never decides whether to
escalate to a human; that is a fixed, auditable set of Python rules in
[`app/decision_engine/engine.py`](app/decision_engine/engine.py). Every tool call and
every decision is logged to `tool_call_logs` / `audit_logs` so any response is
reconstructable after the fact.

## Project layout

| Path | What it is |
|---|---|
| `app/db/models.py` | SQLAlchemy models - customers, orders, order_items, products, tickets, conversations, messages, tool_call_logs, audit_logs, kb_chunks |
| `app/repositories/` | One repository per table - all DB access goes through these |
| `app/tools/` | The agent's closed tool set. `refund_policy.py` is pure, dependency-free logic |
| `app/agent/` | The LangGraph ReAct loop (`graph.py`), prompts, short-term memory shaping, Gemini client |
| `app/decision_engine/` | Deterministic handoff rules - never touched by the LLM |
| `app/services/` | Twilio wrapper (`whatsapp.py`), Gemini embeddings (`embeddings.py`), RAG retrieval (`rag.py`), and the pipeline that wires it all together (`pipeline.py`) |
| `app/knowledge_base/` | `content/*.md` (RAG source documents - `policies.md` for AuraLoop, plus a second unrelated `smilecare_dental.md` demo doc) + `ingest.py` (chunks + embeds every `.md` file into `kb_chunks`, one `source` per file) |
| `app/routers/` | FastAPI routes: the Twilio webhook + read-only dashboard endpoints |
| `scripts/seed_data.py` | Synthetic customers/orders/products/tickets |
| `scripts/simulate_message.py` | Runs one message through the full pipeline without a live Twilio webhook (for demoing the two required scenarios) |

## Setup

1. **Python 3.12** (3.14 currently lacks wheels for several dependencies - a venv is
   already set up at `.venv` using `C:\Program Files\Python312\python.exe`).

   ```
   .venv\Scripts\pip install -r requirements.txt
   ```

2. **Environment**: copy `.env.example` to `.env` and fill in:
   - `DATABASE_URL` / `DATABASE_URL_DIRECT` - Supabase pooled (6543) and direct (5432)
     Postgres connection strings.
   - `GEMINI_API_KEY` - from Google AI Studio.
   - `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_WHATSAPP_FROM` - from your
     Twilio WhatsApp Sandbox.

3. **Database**:
   ```
   .venv\Scripts\python -m alembic upgrade head
   .venv\Scripts\python -m scripts.seed_data
   .venv\Scripts\python -m app.knowledge_base.ingest
   ```

4. **Run the API**:
   ```
   .venv\Scripts\uvicorn app.main:app --reload
   ```
   Point your Twilio WhatsApp Sandbox webhook at `POST /webhook/whatsapp` (via ngrok
   or similar for local dev).

## Testing with real WhatsApp messages (verified working setup)

1. **Expose the local server publicly.** If you're in VS Code, its built-in port
   forwarding (Ports panel → Forward a Port → set Visibility to **Public**) works
   without installing anything - this is what was used for the live verification
   below. ngrok is the usual alternative, but note some antivirus engines flag its
   binary as a false positive; if that happens, VS Code's forwarding or Cloudflare
   Tunnel (`cloudflared`) are drop-in substitutes.
2. **Configure the Sandbox webhook** in the Twilio Console → Messaging → Try it out →
   Send a WhatsApp message → Sandbox settings → "WHEN A MESSAGE COMES IN":
   `https://<your-public-url>/webhook/whatsapp`, method POST.
3. **Join the sandbox** from the phone you'll test with: WhatsApp the `join <code>`
   message (shown on that same Console page) to the sandbox number `+14155238886`.
   This expires after 3 days - rejoin if messages start failing with Twilio error
   63015.
4. Set `TWILIO_WHATSAPP_FROM=whatsapp:+14155238886` in `.env` - the Sandbox always
   sends from this shared number, not any number you own on the account.
5. Text the bot. `scripts/seed_data.py`'s customers won't match your real number, so
   either seed a customer record for your own WhatsApp number (see
   `CustomerRepository` / `OrderRepository` for the shape) or just let the bot treat
   you as a new customer with no order history.

## Verifying the two required scenarios

Without needing a live Twilio webhook, run a seeded customer's message straight
through the pipeline (Twilio send is stubbed to print to the console):

```
.venv\Scripts\python -m scripts.simulate_message --phone "whatsapp:+1555100003" --message "where is my order?"
.venv\Scripts\python -m scripts.simulate_message --phone "whatsapp:+1555100003" --message "I want a refund for my order"
```

(`whatsapp:+15551000NN` for `NN` in `00`-`17` are the seeded customer numbers - see
`scripts/seed_data.py`. `...03`'s latest order is low-value and recently delivered, so
it exercises the clean auto-reply path for both scenarios; most other seeded customers
have at least one high-value order and will instead exercise escalation - see below.)

Both scenarios have been run live end-to-end against real Supabase data and Gemini
(`gemini-3.5-flash-lite`):

- **"Where is my order?"** - the agent calls `lookup_order` (with no order number, so
  it resolves to the customer's most recent order), and replies citing the real
  status/tracking/delivery date. Verified reply: *"Your most recent order
  (ORD-100016) for the DimGray Phone Case Structure was delivered on August 18,
  2026!"* - confidence 1.0, no handoff.
- **"I want a refund"** - the agent calls `lookup_order` then
  `check_refund_eligibility_tool`. Verified: order ORD-100016 ($34.27, delivered
  19 days prior) came back `eligible`; the Decision Engine auto-approved
  (`auto_process_refund: true`), the pipeline flipped the order's status to
  `refunded` in the database, and the agent's reply confirmed it.
- **Escalation paths**, also verified live: a customer whose latest/referenced order
  exceeded the $200 high-value threshold was escalated (`"Order/transaction value
  1600.00 exceeds the 200.00 high-value threshold"`) with a ticket created and the
  agent's draft never sent; a refund request on an order delivered 100 days ago came
  back `ineligible` from the policy tool (*"outside the 30-day return window"*) and
  was escalated on the value threshold that also applied; and a message containing
  "I want to talk to a human" bypassed the agent entirely (zero LLM calls) and went
  straight to a ticket + handoff acknowledgment.

Check `GET /conversations/{id}/audit` afterwards to see the full tool-call and
decision trail for any conversation - every one of the runs above is reconstructable
that way (tool name, input, output, and the Decision Engine's reasoning at each step).

## Tests

```
.venv\Scripts\python -m pytest -q
```

Covers the refund-eligibility policy (pure logic, including window boundaries), the
Decision Engine's escalation rules, and a structural test of the LangGraph agent loop
(tool-call -> artifact capture -> structured finalize) using a scripted fake model, so
it runs without a live Gemini key.

## Known gotchas already handled here

- **Supabase pooled connection needs THREE things, not one** (`app/db/base.py`):
  `NullPool`, AND `connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0,
  "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__"}`. These are three
  independent caches that collide separately under Supavisor's transaction-pooling
  mode: asyncpg's own native cache (`statement_cache_size`), SQLAlchemy's own compiled-
  statement cache (`prepared_statement_cache_size` - a *different*, dialect-specific
  kwarg, easy to confuse with the previous one), and the default statement-naming
  counter, which restarts at `__asyncpg_stmt_1__` per logical connection and collides
  with a leftover prepared statement when the pooler hands a new client the same
  backend socket a prior client used. Fixing only one or two still leaves
  `DuplicatePreparedStatementError`.
- **Supabase's true "direct" host is IPv6-only.** `db.<ref>.supabase.co:5432` will
  fail `getaddrinfo` on any IPv4-only network. Use the session pooler instead for
  migrations - same host as the transaction pooler
  (`aws-0-<region>.pooler.supabase.com`), but port **5432** (session mode) instead of
  **6543** (transaction mode); session mode supports full DDL/session semantics.
- **`sa.Enum(SomeEnum)` sends `.name`, not `.value`, to the database by default.**
  With `class OrderStatus(str, enum.Enum): DELIVERED = "delivered"`, SQLAlchemy will
  try to insert `"DELIVERED"` unless every enum column passes
  `values_callable=lambda e: [m.value for m in e]` (see `app/db/models.py`) - otherwise
  every insert fails with `invalid input value for enum` even though the native
  Postgres enum's values are lowercase and match `.value` exactly.
- **Alembic + native Postgres enums: `create_type=False` must be set at
  *construction* time, on `sqlalchemy.dialects.postgresql.ENUM` specifically** - not
  the generic `sa.Enum` (which silently drops the kwarg during dialect-impl
  adaptation), and not by mutating the attribute after construction (too late - the
  auto-create listener is decided when the type is first bound to a column). Get this
  wrong and creating a table whose column reuses an enum you already created manually
  raises `DuplicateObjectError: type "x" already exists` - see
  `alembic/versions/0001_initial.py`.
- Gemini model/embedding names get retired quickly, and worse, **free-tier quotas
  vary wildly per model** - `gemini-2.5-flash` came back 404 "no longer available to
  new users" against a fresh API key, `gemini-3.6-flash` (the model Google's own 404
  message pointed to) is real but capped at 20 requests/day free tier,
  `gemini-3.5-flash-lite` has a separate, workable quota. `GEMINI_MODEL` and
  `GEMINI_EMBEDDING_MODEL` are env-configurable for exactly this reason - if you hit a
  404, check https://ai.google.dev/gemini-api/docs/models; if you hit a 429
  RESOURCE_EXHAUSTED, try a different model rather than waiting, since quotas are
  tracked per-model.
- Embedding dimension truncation is done manually in `app/services/embeddings.py`
  (truncate + renormalize) as a fallback regardless of whether the API's
  `output_dimensionality` config took effect.
- Every LangGraph node in `app/agent/graph.py` always returns a real,
  schema-declared field - never an empty update dict.
- Twilio signature validation must reconstruct BOTH the scheme AND the host from
  `X-Forwarded-Proto` / `X-Forwarded-Host` (`app/routers/webhook.py::_public_url`) -
  fixing only the scheme still leaves the host as `localhost:PORT` instead of the
  public tunnel hostname (e.g. `xxxxx.devtunnels.ms`) that Twilio actually signed
  against, so the signature check fails 100% of the time even with a correct auth
  token. Confirmed live: real Twilio requests came back `403` until both were fixed;
  logging the tunnel's actual headers (`x-forwarded-proto`, `x-forwarded-host`) is
  the fastest way to debug this if it recurs with a different tunnel provider.
- **Twilio's WhatsApp Sandbox `From` number is a shared, fixed number
  (`+14155238886`)** - not any phone number you own on the account, even one with
  SMS/voice capability. Sending from any other number fails with "Twilio could not
  find a Channel with the specified From address" (error 63007).
- **The Sandbox will only deliver to a recipient who has joined it** by texting
  `join <code>` (shown on the Twilio Console's Sandbox page) to that shared number
  from their own WhatsApp - and that join expires after 3 days. Sending to a
  non-joined (or expired) number fails with error 63015, even though the API call
  to create the message itself returns success (delivery failure is async).
- FastAPI's `request.form()` needs the `python-multipart` package installed even
  for plain `application/x-www-form-urlencoded` bodies (which is what Twilio always
  sends) - without it every webhook POST 500s with `AssertionError: The
  python-multipart library must be installed to use form parsing`.
- Twilio sends and Gemini embedding calls are offloaded via `asyncio.to_thread` -
  both SDKs are synchronous, and calling them directly from an async route would
  block the event loop for every other in-flight request.
