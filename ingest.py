"""Ingest Slippi replay zips (replays/**/*.zip) into SQLite. Reads zips in place."""
import glob
import json
import os
import re
import sqlite3
import sys
import tempfile
import zipfile

from slippi import Game
from slippi.id import CSSCharacter, Stage

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "replays.db")


def char_name(cid):
    try:
        return CSSCharacter(cid).name.replace("_", " ").title()
    except ValueError:
        return f"Unknown({cid})"


def stage_name(sid):
    try:
        return Stage(sid).name.replace("_", " ").title()
    except ValueError:
        return f"Unknown({sid})"


def parse_game(data):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "g.slp")
        with open(path, "wb") as f:
            f.write(data)
        g = Game(path)
        players = {}
        last = g.frames[-1].ports
        for i, pl in enumerate(g.start.players):
            if pl:
                post = last[i].leader.post
                players[i + 1] = dict(char=char_name(pl.character), stocks=post.stocks, dmg=float(post.damage))
        return dict(
            stage=stage_name(g.start.stage),
            frames=len(g.frames),
            end=g.end.method.name if g.end else None,
            players=players,
        )


def main():
    schema = open(os.path.join(ROOT, "schema.sql")).read()
    con = sqlite3.connect(DB)
    con.executescript(schema)
    zips = sorted(glob.glob(os.path.join(ROOT, "replays", "**", "*.zip"), recursive=True))
    n_games = 0
    for zp in zips:
        name = os.path.basename(zp)
        if con.execute("SELECT 1 FROM sets WHERE zip_name=?", (name,)).fetchone():
            continue
        z = zipfile.ZipFile(zp)
        ctx = json.loads(z.read("context.json")) if "context.json" in z.namelist() else {}
        sg = ctx.get("startgg", {})
        ents = ctx.get("players", {})
        e1 = (ents.get("entrant1") or [{}])[0]
        e2 = (ents.get("entrant2") or [{}])[0]
        fs = ctx.get("finalScore", {}).get("slots", [{}, {}])
        port_name = {}
        for s in (ctx.get("scores") or [{}])[0].get("slots", []):
            for p, nm in zip(s.get("ports", []), s.get("displayNames", [])):
                port_name[p] = nm
        cur = con.execute(
            "INSERT INTO sets(zip_name,tournament,event,phase,round_text,best_of,p1_name,p1_chars,p1_score,p2_name,p2_chars,p2_score,duration_ms)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, sg.get("tournament", {}).get("name"), sg.get("event", {}).get("name"),
             sg.get("phase", {}).get("name"), sg.get("set", {}).get("fullRoundText"), ctx.get("bestOf"),
             e1.get("name"), ", ".join(e1.get("characters", [])), fs[0].get("score") if fs else None,
             e2.get("name"), ", ".join(e2.get("characters", [])), fs[1].get("score") if len(fs) > 1 else None,
             ctx.get("durationMs")),
        )
        set_id = cur.lastrowid
        for fn in sorted(x for x in z.namelist() if x.endswith(".slp")):
            try:
                g = parse_game(z.read(fn))
            except Exception as e:  # keep going on a bad file
                print(f"SKIP {name}/{fn}: {e}", file=sys.stderr)
                continue
            ports = sorted(g["players"])
            if len(ports) != 2:
                print(f"SKIP {name}/{fn}: {len(ports)} players", file=sys.stderr)
                continue
            a, b = ports
            pa, pb = g["players"][a], g["players"][b]
            if pa["stocks"] != pb["stocks"]:
                win = a if pa["stocks"] > pb["stocks"] else b
            else:
                win = a if pa["dmg"] < pb["dmg"] else b
            m = re.match(r"(\d+)\s*-", fn)
            con.execute(
                "INSERT INTO games(set_id,file_name,game_number,stage,frames,duration_sec,end_method,"
                "p1_name,p1_port,p1_char,p1_stocks_left,p1_damage,p2_name,p2_port,p2_char,p2_stocks_left,p2_damage,winner)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (set_id, fn, int(m.group(1)) if m else None, g["stage"], g["frames"], g["frames"] / 60,
                 g["end"], port_name.get(a), a, pa["char"], pa["stocks"], pa["dmg"],
                 port_name.get(b), b, pb["char"], pb["stocks"], pb["dmg"], port_name.get(win)),
            )
            n_games += 1
        con.commit()
    print(f"sets: {con.execute('SELECT COUNT(*) FROM sets').fetchone()[0]}, "
          f"games: {con.execute('SELECT COUNT(*) FROM games').fetchone()[0]} (+{n_games} this run)")


if __name__ == "__main__":
    main()
