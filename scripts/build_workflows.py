"""Builds the n8n workflow and credential JSON files for the Shop Analyst demo.

Run: python scripts/build_workflows.py   (reads .env, writes workflows/*.json and build/credentials.json)
"""
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import os
MODEL = os.environ.get("SHOP_MODEL", "llama3.1:latest")
CHAT_ID = "ShopAnalystChat1"
INCIDENTS_ID = "ShopAnalystInc01"

CRED_RO = {"postgres": {"id": "shopDbReadOnly01", "name": "Shop DB (read-only)"}}
CRED_OPS = {"postgres": {"id": "shopDbOpsWrite01", "name": "Shop DB (incident log)"}}
CRED_LLM = {"ollamaApi": {"id": "ollamaLocal00001", "name": "Ollama (local)"}}


def node(name, type_, version, pos, params, **extra):
    n = {"parameters": params, "type": type_, "typeVersion": version, "position": pos,
         "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "shop-analyst/" + name)), "name": name}
    n.update(extra)
    return n


def set_node(name, pos, fields, **extra):
    return node(name, "n8n-nodes-base.set", 3.4, pos, {
        "assignments": {"assignments": [
            {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, name + k)), "name": k, "value": v, "type": t}
            for k, v, t in fields]},
        "options": {}}, **extra)


def cond(left, op, right, typ="string"):
    return {"id": str(uuid.uuid4()), "leftValue": left, "rightValue": right,
            "operator": {"type": typ, "operation": op}}


def if_node(name, pos, condition):
    return node(name, "n8n-nodes-base.if", 2.2, pos, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                       "conditions": [condition], "combinator": "and"},
        "looseTypeValidation": True, "options": {}})


def link(conns, src, dst, out=0, kind="main"):
    outs = conns.setdefault(src, {}).setdefault(kind, [])
    while len(outs) <= out:
        outs.append([])
    outs[out].append({"node": dst, "type": kind, "index": 0})


# ---------------------------------------------------------------- prompts

GUARD_PROMPT = """You sort messages sent to the analytics assistant of an online coffee and tea shop.
The assistant answers questions about the shop's own data: sales and revenue, orders, products and categories,
customers and their countries, reviews and ratings, refunds and cancellations, sales channels.

Reply with ONE JSON object and nothing else:
{"intent": "data" | "smalltalk" | "out_of_scope", "reply": "<text>"}

- data: the message asks something that the shop's data can answer. reply = "".
- smalltalk: greetings, thanks, "what can you do". reply = one friendly sentence that says what you can answer.
- out_of_scope: anything else (general knowledge, coding, other companies, advice). reply = one polite sentence.
"""

ANALYST_PROMPT = """=You are the data analyst of an online coffee and tea shop. You answer the owner's questions
using ONLY rows returned by the run_sql tool in this conversation.

DATABASE (PostgreSQL), table(columns):
{{ $json.schema }}

BUSINESS RULES
- Revenue counts only orders with status paid, shipped or delivered. Use the view order_totals for order revenue.
- Line revenue is order_items.quantity * order_items.unit_price (not products.price).
- Dates: orders.ordered_at is a timestamp; "last month" means the previous calendar month.

HOW TO WORK
1. Write one SELECT for the question and call run_sql. Never INSERT, UPDATE or DELETE.
2. If run_sql returns an error, read it, fix the query and call run_sql again.
3. Answer in 1-4 short sentences. Every number you write must be copied from the rows (you may round money to
   whole euros). If the rows are empty, say that no data matched.
4. Do not show SQL, table names or column names in the answer.
5. The database holds only this shop's data. For benchmarks, market averages or anything outside it, say that
   the data does not contain it. Never type such values into the SQL.
"""

ANALYST_INPUT = ("={{ $json.critique ? 'Your previous answer was rejected by the reviewer: ' + $json.critique"
                 " + '\\nQuery the database again and answer correctly.\\n\\n' : '' }}Question: {{ $json.question }}")

SCHEMA_SQL = """SELECT string_agg(t.table_name || '(' || t.cols || ')', E'\\n' ORDER BY t.table_name) AS schema
FROM (SELECT c.table_name,
             string_agg(c.column_name || ' ' || c.data_type, ', ' ORDER BY c.ordinal_position) AS cols
      FROM information_schema.columns c
      WHERE c.table_schema = 'public'
      GROUP BY c.table_name) t;"""

LOOP_STATE_JS = """// One place that holds the loop state: first pass comes from the router, retries come from "Loop - Add critique".
const prev = $input.first().json;
return [{ json: {
  question: prev.question ?? $('Config - Request').first().json.question,
  schema: $('Analyst - Load schema').first().json.schema,
  attempt: prev.attempt ?? 1,
  critique: prev.critique ?? '',
} }];"""

GUARD_PARSE_JS = """// The model is asked for JSON, but small models wrap it in prose or code fences: dig it out, default to "data".
const text = String($json.text ?? '');
let parsed = {};
const match = text.match(/\\{[\\s\\S]*\\}/);
try { parsed = match ? JSON.parse(match[0]) : {}; } catch (e) { parsed = {}; }
const allowed = ['data', 'smalltalk', 'out_of_scope'];
const intent = allowed.includes(parsed.intent) ? parsed.intent : 'data';
return [{ json: { intent, reply: String(parsed.reply ?? '').trim(),
                  question: $('Config - Request').first().json.question } }];"""

GROUNDING_JS = r"""// Deterministic reviewer: the answer must come from a SQL call, and every number in it must appear in the rows.
const res = $input.first().json;
const state = $('Loop - State').item.json;
const answer = String(res.output ?? '').trim();
const steps = Array.isArray(res.intermediateSteps) ? res.intermediateSteps : [];

const sqlSteps = steps.filter(s => /select/i.test(JSON.stringify(s?.action?.toolInput ?? '')));
const okSteps = sqlSteps.filter(s => !/error/i.test(String(s?.observation ?? '').slice(0, 200)));

const numbersIn = text => (String(text).match(/-?\d[\d,]*(?:\.\d+)?/g) ?? [])
  .map(n => Number(n.replace(/,/g, ''))).filter(n => Number.isFinite(n));
const close = (a, b) => Math.abs(a - b) <= Math.max(1, Math.abs(a) * 0.005);
// A constant typed into the SQL ("25.00 AS market_average") comes back as a row value, but it is not data.
const sqlConstants = numbersIn(okSteps.map(s => JSON.stringify(s.action.toolInput)).join(' '));
const evidence = numbersIn(okSteps.map(s => s.observation).join(' ') + ' ' + state.question);
const fromData = v => evidence.some(e => close(e, v)) && !sqlConstants.some(k => close(k, v));
const significant = v => Math.abs(v) > 10 && !(v >= 2000 && v <= 2100);

const problems = [];
if (!answer) problems.push('The answer is empty.');
if (!sqlSteps.length) problems.push('You answered without calling run_sql. Query the database first.');
else if (!okSteps.length) problems.push('Every query failed. Fix the SQL using the error message.');
else {
  const numbers = numbersIn(answer).filter(significant);
  const typedIn = numbers.filter(v => sqlConstants.some(k => close(k, v)));
  const missing = numbers.filter(v => !typedIn.includes(v) && !fromData(v));
  if (typedIn.length) problems.push('These numbers were written into the SQL as constants, they are not data: '
    + typedIn.join(', ') + '. If the database cannot answer part of the question, say so.');
  if (missing.length) problems.push('These numbers are not in the query results: ' + missing.join(', ') + '.');
}

return [{ json: {
  verdict: problems.length ? 'RETRY' : 'PASS',
  critique: problems.join(' '),
  answer,
  question: state.question,
  attempt: state.attempt,
  sql_calls: sqlSteps.length,
} }];"""


# ---------------------------------------------------------------- workflow 1: chat analyst

def chat_workflow():
    n, c = [], {}
    add = n.append
    add(node("Trigger - Chat", "@n8n/n8n-nodes-langchain.chatTrigger", 1.1, [-1600, 200],
             {"public": True, "mode": "hostedChat", "options": {"responseMode": "lastNode"}}, webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "chat-hook"))))
    add(set_node("Config - Request", [-1380, 200], [
        ("question", "={{ $json.chatInput }}", "string"),
        ("session_id", "={{ $json.sessionId }}", "string"),
        ("max_attempts", 3, "number")]))
    add(node("Guard - Classify question", "@n8n/n8n-nodes-langchain.chainLlm", 1.7, [-1160, 200], {
        "promptType": "define", "text": "={{ $json.question }}",
        "messages": {"messageValues": [{"message": GUARD_PROMPT}]}}, onError="continueRegularOutput"))
    add(node("Guard - Parse intent", "n8n-nodes-base.code", 2, [-860, 200], {"jsCode": GUARD_PARSE_JS}))
    rules = [{"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                             "conditions": [cond("={{ $json.intent }}", "equals", v)], "combinator": "and"},
              "renameOutput": True, "outputKey": v} for v in ("data", "smalltalk", "out_of_scope")]
    add(node("Guard - Route", "n8n-nodes-base.switch", 3.2, [-640, 200], {"rules": {"values": rules}, "options": {}}))
    add(set_node("Reply - Smalltalk", [-380, 420], [
        ("output", "={{ $json.reply || 'Hi! Ask me about sales, products, customers, orders or reviews.' }}", "string")]))
    add(set_node("Reply - Out of scope", [-380, 620], [
        ("output", "I can only answer questions about this shop's data: sales, products, customers, orders and reviews.",
         "string")]))
    add(node("Analyst - Load schema", "n8n-nodes-base.postgres", 2.6, [-380, 100],
             {"operation": "executeQuery", "query": SCHEMA_SQL, "options": {}},
             credentials=CRED_RO, executeOnce=True, retryOnFail=True, maxTries=2))
    add(node("Loop - State", "n8n-nodes-base.code", 2, [-160, 100], {"jsCode": LOOP_STATE_JS}))
    add(node("Analyst - Agent", "@n8n/n8n-nodes-langchain.agent", 2.2, [80, 100], {
        "promptType": "define", "text": ANALYST_INPUT,
        "options": {"systemMessage": ANALYST_PROMPT, "maxIterations": 6, "returnIntermediateSteps": True}},
        onError="continueErrorOutput"))
    add(node("Model - Ollama", "@n8n/n8n-nodes-langchain.lmChatOllama", 1, [-560, 520],
             {"model": MODEL, "options": {"temperature": 0}}, credentials=CRED_LLM))
    add(node("Memory - Chat window", "@n8n/n8n-nodes-langchain.memoryBufferWindow", 1.3, [80, 380], {
        "sessionIdType": "customKey", "sessionKey": "={{ $('Config - Request').first().json.session_id }}",
        "contextWindowLength": 6}))
    add(node("Tool - run_sql", "n8n-nodes-base.postgresTool", 2.6, [280, 380], {
        "descriptionType": "manual",
        "toolDescription": "Runs ONE read-only PostgreSQL SELECT on the shop database and returns the rows as JSON. "
                           "On a mistake it returns the database error, so you can fix the query.",
        "operation": "executeQuery",
        "query": "={{ $fromAI('sql', 'One PostgreSQL SELECT statement', 'string') }}",
        "options": {}}, credentials=CRED_RO))
    add(node("Review - Grounding check", "n8n-nodes-base.code", 2, [440, 0], {"jsCode": GROUNDING_JS}))
    add(if_node("Review - Passed?", [660, 0], cond("={{ $json.verdict }}", "equals", "PASS")))
    add(set_node("Reply - Answer", [900, -120], [("output", "={{ $json.answer }}", "string")]))
    add(if_node("Review - Attempts left?", [900, 120], cond(
        "={{ $json.attempt }}", "lt", "={{ $('Config - Request').first().json.max_attempts }}", "number")))
    add(set_node("Loop - Add critique", [1140, 40], [
        ("question", "={{ $json.question }}", "string"),
        ("critique", "={{ $json.critique }}", "string"),
        ("attempt", "={{ $json.attempt + 1 }}", "number")]))
    add(set_node("Reply - Could not verify", [1140, 240], [(
        "output", "=I could not confirm this answer against the data after {{ $json.attempt }} attempts, so I'd rather "
                  "not guess. Try asking more specifically (a period, a product, a country).", "string")]))
    add(set_node("Ops - Incident payload", [440, 260], [
        ("workflow_name", "={{ $workflow.name }}", "string"),
        ("failed_node", "Analyst - Agent", "string"),
        ("error_message", "={{ $json.error?.message ?? $json.error ?? 'unknown error' }}", "string"),
        ("execution_url", "={{ $execution.id }}", "string")]))
    add(node("Ops - Report incident", "n8n-nodes-base.executeWorkflow", 1.2, [660, 260], {
        "source": "database", "workflowId": {"__rl": True, "value": INCIDENTS_ID, "mode": "id"},
        "workflowInputs": {"mappingMode": "defineBelow", "value": {}, "matchingColumns": [], "schema": [],
                           "attemptToConvertTypes": False, "convertFieldsToString": True},
        "options": {"waitForSubWorkflow": False}}))
    add(set_node("Reply - Technical issue", [900, 360], [
        ("output", "Something went wrong on my side while querying the data. The team has been notified, "
                   "please try again in a minute.", "string")]))

    for a, b in [("Trigger - Chat", "Config - Request"), ("Config - Request", "Guard - Classify question"),
                 ("Guard - Classify question", "Guard - Parse intent"), ("Guard - Parse intent", "Guard - Route"),
                 ("Analyst - Load schema", "Loop - State"), ("Loop - State", "Analyst - Agent"),
                 ("Review - Grounding check", "Review - Passed?"), ("Loop - Add critique", "Loop - State"),
                 ("Ops - Incident payload", "Ops - Report incident"),
                 ("Ops - Report incident", "Reply - Technical issue")]:
        link(c, a, b)
    link(c, "Guard - Route", "Analyst - Load schema", 0)
    link(c, "Guard - Route", "Reply - Smalltalk", 1)
    link(c, "Guard - Route", "Reply - Out of scope", 2)
    link(c, "Analyst - Agent", "Review - Grounding check", 0)
    link(c, "Analyst - Agent", "Ops - Incident payload", 1)
    link(c, "Review - Passed?", "Reply - Answer", 0)
    link(c, "Review - Passed?", "Review - Attempts left?", 1)
    link(c, "Review - Attempts left?", "Loop - Add critique", 0)
    link(c, "Review - Attempts left?", "Reply - Could not verify", 1)
    link(c, "Model - Ollama", "Guard - Classify question", kind="ai_languageModel")
    link(c, "Model - Ollama", "Analyst - Agent", kind="ai_languageModel")
    link(c, "Memory - Chat window", "Analyst - Agent", kind="ai_memory")
    link(c, "Tool - run_sql", "Analyst - Agent", kind="ai_tool")

    return {"id": CHAT_ID, "name": "Shop Analyst - Chat", "nodes": n, "connections": c, "active": False,
            "settings": {"executionOrder": "v1", "errorWorkflow": INCIDENTS_ID}, "pinData": {}}


# ---------------------------------------------------------------- workflow 2: incidents

def incidents_workflow():
    n, c = [], {}
    n.append(node("Trigger - Workflow failed", "n8n-nodes-base.errorTrigger", 1, [-600, 0], {}))
    n.append(node("Trigger - Reported by workflow", "n8n-nodes-base.executeWorkflowTrigger", 1.1, [-600, 220],
                  {"inputSource": "passthrough"}))
    n.append(set_node("Format - Incident", [-360, 100], [
        ("workflow_name", "={{ $json.workflow?.name ?? $json.workflow_name ?? 'unknown' }}", "string"),
        ("failed_node", "={{ $json.execution?.lastNodeExecuted ?? $json.failed_node ?? 'unknown' }}", "string"),
        ("error_message", "={{ $json.execution?.error?.message ?? $json.error_message ?? 'no message' }}", "string"),
        ("execution_url", "={{ $json.execution?.url ?? $json.execution_url ?? '' }}", "string")]))
    n.append(node("Log - Save incident", "n8n-nodes-base.postgres", 2.6, [-120, 100], {
        "schema": {"__rl": True, "value": "ops", "mode": "name"},
        "table": {"__rl": True, "value": "incidents", "mode": "name"},
        "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []},
        "options": {}}, credentials=CRED_OPS, retryOnFail=True, maxTries=3, waitBetweenTries=2000))
    link(c, "Trigger - Workflow failed", "Format - Incident")
    link(c, "Trigger - Reported by workflow", "Format - Incident")
    link(c, "Format - Incident", "Log - Save incident")
    return {"id": INCIDENTS_ID, "name": "Shop Analyst - Incidents", "nodes": n, "connections": c, "active": False,
            "settings": {"executionOrder": "v1"}, "pinData": {}}


def credentials(env):
    pg = {"host": "shop-db", "database": "shop", "port": 5432, "ssl": "disable"}
    return [
        {"id": CRED_RO["postgres"]["id"], "name": CRED_RO["postgres"]["name"], "type": "postgres",
         "data": {**pg, "user": "analyst_ro", "password": env["ANALYST_RO_PASSWORD"]}},
        {"id": CRED_OPS["postgres"]["id"], "name": CRED_OPS["postgres"]["name"], "type": "postgres",
         "data": {**pg, "user": "ops_writer", "password": env["OPS_WRITER_PASSWORD"]}},
        {"id": CRED_LLM["ollamaApi"]["id"], "name": CRED_LLM["ollamaApi"]["name"], "type": "ollamaApi",
         "data": {"baseUrl": "http://host.docker.internal:11434"}},
    ]


if __name__ == "__main__":
    env = dict(l.split("=", 1) for l in (ROOT / ".env").read_text().split() if "=" in l)
    (ROOT / "workflows").mkdir(exist_ok=True)
    (ROOT / "build").mkdir(exist_ok=True)
    for wf, file in [(chat_workflow(), "shop-analyst-chat.json"), (incidents_workflow(), "shop-analyst-incidents.json")]:
        (ROOT / "workflows" / file).write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "build" / "credentials.json").write_text(json.dumps(credentials(env), indent=2), encoding="utf-8")
    print("ok")
