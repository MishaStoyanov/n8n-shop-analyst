# Shop Analyst (n8n demo)

Ask questions about an online coffee and tea shop in plain English and get answers backed by SQL.
Runs fully local: n8n and Postgres in Docker, the model in Ollama.

## What is inside

**Shop Analyst - Chat**

```
Chat ─▶ Config ─▶ Guard: classify ─▶ Guard: route ─┬─ data ──────▶ Load schema ─▶ Loop state ─▶ Analyst agent ─┬─▶ Grounding check ─▶ Passed? ─┬─ yes ─▶ Answer
                                                   ├─ smalltalk ─▶ Reply                     ▲   (run_sql tool,  │                              └─ no ──▶ Attempts left? ─┬─ yes ─▶ Add critique ─┐
                                                   └─ off-topic ─▶ Reply                     │    chat memory)   │                                                        └─ no ──▶ "Could not verify"
                                                                                             └───────────────────│───────────────────────────────────────────────────────────────────────────┘
                                                                                                                 └─ error ─▶ Report incident ─▶ "Technical issue" reply
```

- **Guard** sorts the message (data / smalltalk / off-topic). If the classifier itself fails, the message goes on as a data question.
- **Analyst** gets the schema up front (one query, not a tool call) and a single `run_sql` tool. The tool returns database errors to the agent, so it can fix its own SQL.
- **Grounding check** is plain code, not another LLM call: the answer must come from a query, every number in it must appear in the returned rows, and numbers typed into the SQL as constants do not count as data. On failure the critique goes back to the agent, up to 3 attempts, then the user gets an honest "could not verify".
- **Failures** of the agent (model down, timeout) give the user a polite reply and log an incident.

**Shop Analyst - Incidents**: called by the chat workflow, and set as its error workflow. Writes to `ops.incidents`.

## Safety

- The agent connects as `analyst_ro`: SELECT only, every transaction read-only, 10 s statement timeout.
- Incidents are written by `ops_writer`, which can only touch `ops.incidents`.

## Run

```bash
# 1. secrets for the local database roles
python -c "import secrets;print('\n'.join(f'{k}={secrets.token_urlsafe(16)}' for k in ['SHOP_ADMIN_PASSWORD','ANALYST_RO_PASSWORD','OPS_WRITER_PASSWORD']))" > .env
# 2. start Postgres (seeded with ~3000 synthetic orders) and n8n
docker compose up -d
# 3. Ollama on the host
ollama pull llama3.1
# 4. generate and import credentials and workflows
python scripts/build_workflows.py
MSYS_NO_PATHCONV=1 docker cp build/credentials.json n8n:/tmp/creds.json
docker exec n8n n8n import:credentials --input=/tmp/creds.json
docker exec n8n n8n import:workflow --separate --input=/workflows
docker exec n8n n8n publish:workflow --id=ShopAnalystInc01
docker exec n8n n8n publish:workflow --id=ShopAnalystChat1
docker restart n8n
```

Open http://localhost:5678, open **Shop Analyst - Chat** and use the chat button.

## Replaying a failure

`demo/pinned-hallucination.json` is a real output in which the model put an invented benchmark into its SQL
(`25.00 AS avg_online_coffee_shop`). Pin it on **Analyst - Agent** (Edit output, paste) and run the chat: the grounding check rejects it,
the loop retries, and after three attempts the user gets "could not verify" instead of a made-up number.
