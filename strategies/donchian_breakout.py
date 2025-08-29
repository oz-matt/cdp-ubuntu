#!/usr/bin/env python3
"""
Donchian Breakout Strategy (Long-only, 5m)

Rules:
- 200 EMA filter: only take longs when close > EMA200
- Entry: breakout above N-high (e.g., 55)
- Exit: close below M-low (e.g., 20) or below EMA200
- Position sizing: target up to 100% in regime, rebalance on drift

Run via: python backtest.py donchian_breakout
Class name: DonchianBreakoutStrategy
"""

from typing import Dict, Tuple, Deque
from collections import deque

from strategies.simple_grid import TradingStrategy


class DonchianBreakoutStrategy(TradingStrategy):
    def __init__(
        self,
        initial_balance: float = 1000.0,
        fee_rate: float = 0.001,
        breakout_lookback: int = 55,
        exit_lookback: int = 20,
        ema_period: int = 200,
        rebalance_threshold: float = 0.02,
        max_trade_fraction: float = 0.3,
        target_allocation: float = 0.98,
    ):
        self.breakout_lookback = breakout_lookback
        self.exit_lookback = exit_lookback
        self.ema_period = ema_period
        self.rebalance_threshold = rebalance_threshold
        self.max_trade_fraction = max_trade_fraction
        self._ema = None

        self._high_window: Deque[float] = deque(maxlen=breakout_lookback)
        self._low_window: Deque[float] = deque(maxlen=exit_lookback)
        self._last_ts = None  # not used now
        self._target_allocation = target_allocation

        super().__init__(initial_balance=initial_balance, fee_rate=fee_rate)

    def _ema_update(self, prev: float, price: float, period: int) -> float:
        k = 2 / (period + 1)
        if prev is None:
            return price
        return price * k + prev * (1 - k)

    def _update(self, data: Dict):
        c = data['close']
        h = data['high']
        l = data['low']
        self._ema = self._ema_update(self._ema, c, self.ema_period)
        self._high_window.append(h)
        self._low_window.append(l)
        # process each tick; no timestamp dependency

    def _in_regime(self, price: float) -> bool:
        if self._ema is None:
            return False
        return price > self._ema

    def _current_allocation(self, price: float) -> float:
        total_value = self.portfolio.cash + self.portfolio.eth * price
        if total_value <= 0:
            return 0.0
        return (self.portfolio.eth * price) / total_value

    def _needs_rebalance(self, price: float, target_alloc: float) -> Tuple[bool, float]:
        current = self._current_allocation(price)
        drift = target_alloc - current
        return (abs(drift) >= self.rebalance_threshold, drift)

    def should_buy(self, current_price: float, data: Dict) -> Tuple[bool, str]:
        self._update(data=data)
        if not self._in_regime(current_price):
            return False, "Below EMA filter"
        if len(self._high_window) < self._high_window.maxlen:
            return False, "Insufficient history"
        breakout_level = max(self._high_window)
        if current_price > breakout_level:
            need, drift = self._needs_rebalance(current_price, self._target_allocation)
            if need and drift > 0:
                return True, f"Breakout above {breakout_level:.2f} and drift {drift:+.2%}"
        return False, "No buy"

    def should_sell(self, current_price: float, data: Dict) -> Tuple[bool, str]:
        self._update(data=data)
        # Exit if below EMA or below M-low
        exit_trigger = False
        reason = "Hold"
        if self._ema is not None and current_price < self._ema:
            exit_trigger = True
            reason = "Exit: below EMA"
        if len(self._low_window) == self._low_window.maxlen:
            exit_level = min(self._low_window)
            if current_price < exit_level:
                exit_trigger = True
                reason = f"Exit: below {self.exit_lookback}-low {exit_level:.2f}"

        if exit_trigger:
            return True, reason

        # Rebalance down if drifted above target
        need, drift = self._needs_rebalance(current_price, self._target_allocation)
        if need and drift < 0:
            return True, f"Rebalance down (drift {drift:+.2%})"
        return False, "Hold"

    def get_trade_amount(self, current_price: float, action: str) -> float:
        total_value = self.portfolio.cash + self.portfolio.eth * current_price
        target_value = self._target_allocation * total_value
        current_value = self.portfolio.eth * current_price
        delta_value = target_value - current_value

        if action == 'BUY' and delta_value > 0:
            desired = min(delta_value, self.portfolio.cash)
            desired = min(desired, self.max_trade_fraction * self.portfolio.cash)
            return max(0.0, desired)

        if action == 'SELL' and delta_value < 0:
            desired = min(-delta_value, self.portfolio.eth * current_price)
            desired = min(desired, self.max_trade_fraction * self.portfolio.eth * current_price)
            return max(0.0, desired / current_price if current_price > 0 else 0.0)

        return 0.0

    def process_tick(self, timestamp: int, datetime_str: str, price_data: Dict):
        # Override base to avoid initial forced 50% buy
        current_price = price_data['close']

        # Update indicators first
        self._update(price_data)

        should_buy, buy_reason = self.should_buy(current_price, price_data)
        should_sell, sell_reason = self.should_sell(current_price, price_data)

        if should_buy and not should_sell:
            amount = self.get_trade_amount(current_price, 'BUY')
            if amount > 0:
                self.execute_trade(timestamp, datetime_str, current_price, 'BUY', amount, buy_reason)
        elif should_sell and not should_buy:
            amount = self.get_trade_amount(current_price, 'SELL')
            if amount > 0:
                self.execute_trade(timestamp, datetime_str, current_price, 'SELL', amount, sell_reason)

        self.update_portfolio_value(current_price)

