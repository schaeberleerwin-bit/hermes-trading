from hermes_trading.reflect import fallback_change

def test_fallback_changes_one_path():
    strat={"strategy":{"min_spread":0.0001,"gamma":0.1},"risk":{"stop_loss_percent":0.05}}
    goal={"target_return_30d":0.05,"max_drawdown":0.08}
    path, new, reason = fallback_change(strat, [{"return_pct":-0.1,"equity_after":9990}], goal)
    assert path.count(".") == 1
    assert new != 0.0001
