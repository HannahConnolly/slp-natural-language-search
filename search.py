"""Natural-language search over replays.db.

Usage: python search.py "Fox vs Falco on Battlefield"
Needs ANTHROPIC_API_KEY in the environment.
"""
import json
import os
import re
import sqlite3
import sys

import anthropic

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "replays.db")
MODEL = "claude-haiku-5-5"
MAX_ROWS = 50

SYSTEM = """You translate questions about Super Smash Bros. Melee tournament replays into one SQLite SELECT query.

Schema:
{schema}

Notes:
- Characters are stored like 'Captain Falcon', 'Fox', 'Falco', 'Jigglypuff', 'Ice Climbers', 'Dr. Mario'. Stages like 'Battlefield', 'Final Destination', 'Fountain Of Dreams', 'Dream Land N64', 'Yoshis Story', 'Pokemon Stadium'.
- p1/p2 are arbitrary slots, so a character or player may be in either: always check both sides (e.g. (p1_char='Fox' OR p2_char='Fox')).
- 'Falcon' means 'Captain Falcon'. Match names with LIKE and COLLATE NOCASE.
- Always JOIN games g with sets s ON s.id = g.set_id and select readable columns: s.round_text, g.game_number, g.stage, p1/p2 names and characters, g.winner, g.duration_sec, g.file_name, s.zip_name.
- Only SELECT. Add LIMIT {limit} unless the question is an aggregate.
Reply with JSON only: {{"sql": "..."}} or {{"error": "why the question can't be answered from this data"}}."""


def schema_text():
    return open(os.path.join(ROOT, "schema.sql")).read()


def ask_model(question):
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=800,
        system=SYSTEM.format(schema=schema_text(), limit=MAX_ROWS),
        messages=[{"role": "user", "content": question}],
    )
    text = msg.content[0].text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"unparseable model reply: {text[:200]}")
    return json.loads(m.group(0))


def run_readonly(sql):
    sql = sql.strip().rstrip(";")
    if not re.match(r"(?is)^\s*(select|with)\b", sql) or ";" in sql:
        raise ValueError("only a single SELECT is allowed")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.execute("PRAGMA query_only = ON")
    # Deny everything except reads and function calls.
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    con.set_authorizer(lambda action, *a: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
    # Abort runaway queries.
    steps = [0]
    def guard():
        steps[0] += 1
        return 1 if steps[0] > 2000 else 0
    con.set_progress_handler(guard, 10000)
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchmany(MAX_ROWS)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY first (https://console.anthropic.com/settings/keys).")
    question = " ".join(sys.argv[1:])
    reply = ask_model(question)
    if "error" in reply:
        sys.exit(reply["error"])
    sql = reply["sql"]
    print(f"-- {sql}\n")
    cols, rows = run_readonly(sql)
    if not rows:
        print("No matches.")
        return
    print(" | ".join(cols))
    for r in rows:
        print(" | ".join("" if v is None else (f"{v:.1f}" if isinstance(v, float) else str(v)) for v in r))
    print(f"\n{len(rows)} row(s)")


if __name__ == "__main__":
    main()
