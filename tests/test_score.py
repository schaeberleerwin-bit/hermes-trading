from hermes_trading.score import score

def test_score_bounds():
    goal={"target_return_30d":0.05,"max_drawdown":0.08,"min_sharpe":1.2,"failure_below":-0.04}
    trades=[{"return_pct":0.4},{"return_pct":0.2},{"return_pct":-0.1}]
    s=score(trades, goal)
    assert -1 <= s <= 1
