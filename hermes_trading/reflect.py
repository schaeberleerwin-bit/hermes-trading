from __future__ import annotations
import argparse, json, shutil, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
import yaml
from .score import score

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"

def load_yaml(path: Path) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}

def save_yaml(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(obj, f, sort_keys=False)

def read_trades(limit=25):
    path = STATE / "trades.jsonl"
    if not path.exists():
        return []
    rows=[]
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows[-limit:]

def bump_version(strategy: dict) -> str:
    cur = str(strategy.get("version", "01"))
    nxt = int(cur) + 1 if cur.isdigit() else 2
    strategy["version"] = f"{nxt:02d}"
    return strategy["version"]

def archive_prior(strategy: dict):
    old = str(strategy.get("version", "01"))
    hist = STATE / "history" / f"v{int(old):04d}.yaml"
    hist.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(STATE / "strategy.yaml", hist)
    return hist

def append_hypothesis(obj: dict):
    with open(STATE / "hypotheses.jsonl", "a") as f:
        f.write(json.dumps(obj, sort_keys=True) + "\n")

def set_path(obj: dict, dotted: str, value):
    cur = obj
    parts = dotted.split(".")
    for p in parts[:-1]:
        cur = cur[p]
    old = cur[parts[-1]]
    cur[parts[-1]] = value
    return old

def fallback_change(strategy: dict, trades: list, goal: dict):
    realised = sum(float(t.get("return_pct", 0))/100.0 for t in trades)
    # drawdown from equity_after if available
    equities = [float(t.get("equity_after", t.get("equity_before", 10000))) for t in trades] or [10000]
    peak = equities[0]
    dd = 0.0
    for e in equities:
        peak=max(peak,e); dd=min(dd,(e-peak)/peak if peak else 0)
    if abs(dd) > float(goal["max_drawdown"]):
        path = "risk.stop_loss_percent"
        new = max(0.005, round(float(strategy["risk"]["stop_loss_percent"]) - 0.002, 4))
        reason = "drawdown exceeded max; tightened stop loss by 0.2 percentage points"
    elif realised < float(goal["target_return_30d"]):
        path = "strategy.min_spread"
        new = max(0.00001, round(float(strategy["strategy"]["min_spread"]) * 0.98, 6))
        reason = "realised return below target; loosened minimum spread by 2% to seek more fills"
    else:
        path = "strategy.gamma"
        new = round(float(strategy["strategy"]["gamma"]) * 1.02, 6)
        reason = "target met; raised risk aversion slightly to protect gains"
    return path, new, reason

def hermes_change(strategy: dict, trades: list, goal: dict):
    prompt = f"""You are improving a paper-mode Avellaneda-Stoikov market maker. Change exactly ONE scalar variable in strategy.yaml. Return only JSON with keys path, value, reason.\nGoal: {json.dumps(goal)}\nCurrent strategy YAML:\n{yaml.safe_dump(strategy, sort_keys=False)}\nLatest trades JSON:\n{json.dumps(trades[-25:], indent=2)}"""
    cp = subprocess.run(["hermes", "chat", "-q", prompt], text=True, capture_output=True, timeout=180)
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr or cp.stdout)
    text = cp.stdout.strip()
    # Strip ANSI escape codes (colour/spinner output from hermes chat)
    import re
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    # Parse the FIRST JSON object in the response that has the required keys.
    # The echoed "Query: ..." line contains the prompt verbatim (with its own
    # braces) and must not be used — find a candidate object that contains
    # both 'path' and 'value'.
    decoder = json.JSONDecoder()
    pos = 0
    chosen = None
    while True:
        i = text.find("{", pos)
        if i < 0:
            break
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            pos = i + 1
            continue
        if isinstance(obj, dict) and "path" in obj and "value" in obj:
            p = obj["path"]
            # Reject candidates that echo an absolute filesystem path (the model
            # sometimes returns "C:/.../state/strategy.risk.stop_loss_percent").
            if not isinstance(p, str) or (len(p) >= 2 and p[1] == ":") or p.startswith("/"):
                pos = end
                continue
            chosen = (obj, end)
            break
        pos = end
    if chosen is None:
        raise RuntimeError(f"Hermes did not return a valid hypothesis JSON: {text[:500]}")
    obj, _end = chosen
    return obj["path"], obj["value"], obj.get("reason", "Hermes hypothesis")

def reflect(mode: str):
    goal = load_yaml(STATE / "goal.yaml")
    strategy = load_yaml(STATE / "strategy.yaml")
    trades = read_trades(25)
    before_score = score(trades, goal)
    if mode == "hermes":
        path, new, reason = hermes_change(strategy, trades, goal)
    else:
        path, new, reason = fallback_change(strategy, trades, goal)
    old = set_path(strategy, path, new)
    archive = archive_prior(strategy)
    version = bump_version(strategy)
    save_yaml(STATE / "strategy.yaml", strategy)
    hyp = {"ts": datetime.now(timezone.utc).isoformat(), "mode": mode, "version": version, "changed": path, "old": old, "new": new, "reason": reason, "score_before": before_score, "trades_used": len(trades), "archive": str(archive), "one_variable_only": True}
    append_hypothesis(hyp)
    print(json.dumps(hyp, indent=2))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--fallback", action="store_true")
    g.add_argument("--hermes", action="store_true")
    args = ap.parse_args()
    reflect("hermes" if args.hermes else "fallback")
