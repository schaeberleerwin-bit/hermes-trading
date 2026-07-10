from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
CADENCE = 5

def count_trades() -> int:
    p = STATE / "trades.jsonl"
    if not p.exists():
        return 0
    return sum(1 for line in p.read_text().splitlines() if line.strip())

def read_last() -> int:
    p = STATE / "last_reflection_count.txt"
    if not p.exists():
        return 0
    try:
        return int(p.read_text().strip() or "0")
    except ValueError:
        return 0

def main():
    current = count_trades()
    last = read_last()
    new = current - last
    print(f"Hermes trading brain check: trades={current}, last_reflection_count={last}, new={new}")
    if new < CADENCE:
        print("Standby: not enough new closed trades for reflection.")
        return 0
    cmd = ["uv", "run", "python", "-m", "hermes_trading.reflect", "--hermes"]
    env = dict(**__import__('os').environ)
    env.pop("VIRTUAL_ENV", None)
    env["UV_PROJECT_ENVIRONMENT"] = ".venv"
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, text=True, capture_output=True, timeout=300)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    (STATE / "last_reflection_count.txt").write_text(str(current) + "\n")
    print(f"Reflection complete. last_reflection_count={current}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
