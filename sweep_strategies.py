#!/usr/bin/env python3
"""
Parameter sweep runner (Windows-friendly)

Runs multiple strategies with different parameter grids using the in-process
backtester (silent mode). Summarizes and prints the best configuration.

Usage examples:
  python sweep_strategies.py --max-days 180 --sleep-sec 0 --amount 1000

On Windows PowerShell you can also set env vars:
  $env:BACKTEST_MAX_DAYS=180; $env:BACKTEST_SLEEP_SEC=0; python sweep_strategies.py
"""

import os
import argparse
import importlib
from typing import Dict, Any, List, Tuple

import pandas as pd

from backtest import load_all_eth_data, calculate_hodl_performance, run_strategy_backtest


def run_one(
    df: pd.DataFrame,
    strategy_path: str,
    cls_name: str,
    amount: float,
    kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    module = importlib.import_module(strategy_path)
    strategy_cls = getattr(module, cls_name)
    return run_strategy_backtest(
        df=df,
        strategy_or_class=strategy_cls,
        investment_amount=amount,
        silent=True,
        strategy_kwargs=kwargs,
    )


def grid(params: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    from itertools import product
    keys = list(params.keys())
    values = [params[k] for k in keys]
    combos = []
    for items in product(*values):
        combos.append({k: v for k, v in zip(keys, items)})
    return combos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--amount', type=float, default=1000.0)
    parser.add_argument('--max-days', type=int, default=None)
    parser.add_argument('--sleep-sec', type=float, default=None)
    args = parser.parse_args()

    if args.max_days is not None:
        os.environ['BACKTEST_MAX_DAYS'] = str(args.max_days)
    if args.sleep_sec is not None:
        os.environ['BACKTEST_SLEEP_SEC'] = str(args.sleep_sec)

    df = load_all_eth_data()
    if df is None:
        raise SystemExit(1)
    hodl = calculate_hodl_performance(df, args.amount)

    experiments: List[Tuple[str, str, Dict[str, Any]]] = []

    # EMA+ATR Trend sweeps
    ema_atr_grid = grid({
        'short_ema_period': [34, 50, 72],
        'long_ema_period': [144, 200, 288],
        'atr_period': [14, 21],
        'risk_atr_multiple': [2.5, 3.0, 3.5],
        'max_allocation': [0.9, 0.95, 0.99],
        'min_allocation': [0.0, 0.05],
        'rebalance_threshold': [0.01, 0.02, 0.05],
        'max_trade_fraction': [0.2, 0.3],
    })
    for kw in ema_atr_grid:
        experiments.append(('strategies.ema_atr_trend', 'EmaAtrTrendStrategy', kw))

    # Donchian sweeps
    donchian_grid = grid({
        'breakout_lookback': [40, 55, 80],
        'exit_lookback': [10, 20, 30],
        'ema_period': [150, 200, 250],
        'target_allocation': [0.9, 0.98, 1.0],
        'rebalance_threshold': [0.01, 0.02, 0.05],
        'max_trade_fraction': [0.2, 0.3],
    })
    for kw in donchian_grid:
        experiments.append(('strategies.donchian_breakout', 'DonchianBreakoutStrategy', kw))

    # Simple grid sanity sweep (optional)
    simple_grid_grid = grid({
        'price_threshold': [0.005, 0.01, 0.02],
        'trade_size_percent': [0.05, 0.1, 0.15],
    })
    for kw in simple_grid_grid:
        experiments.append(('strategies.simple_grid', 'SimpleGridStrategy', kw))

    results = []
    for mod, cls, kw in experiments:
        try:
            res = run_one(df, mod, cls, args.amount, kw)
            results.append((mod, cls, kw, res))
        except Exception as e:
            print(f"❌ Failed {mod}.{cls} {kw}: {e}")

    # Rank by final value
    results.sort(key=lambda x: x[3]['final_value'], reverse=True)
    best = results[0] if results else None

    print("\n=== SWEEP SUMMARY ===")
    print(f"HODL final: ${hodl['final_value']:,.2f} | Return: {hodl['percent_return']:.2f}%")
    if best:
        mod, cls, kw, res = best
        print(f"BEST: {mod}.{cls} {kw}")
        print(f"Final: ${res['final_value']:,.2f} | Return: {res['total_return']:.2f}% | MDD: {res['max_drawdown']:.2f}% | Trades: {res['total_trades']}")
    else:
        print("No successful runs.")

    # Print top 5
    print("\nTop 5:")
    for i, (mod, cls, kw, res) in enumerate(results[:5], 1):
        print(f"{i}. {mod}.{cls} {kw} => ${res['final_value']:,.0f} | {res['total_return']:.1f}% | MDD {res['max_drawdown']:.1f}% | trades {res['total_trades']}")

    # Suggested command to run best on full data (Windows example)
    if best:
        mod, cls, kw, res = best
        strat_name = mod.split('.')[-1]
        args_kv = ' '.join([f"{k}={v}" for k, v in kw.items()])
        print("\nRun best on full data (Windows PowerShell):")
        print(f".\\.venv\\Scripts\\python.exe .\\backtest.py {strat_name} {args.amount} {args_kv}")


if __name__ == "__main__":
    main()

