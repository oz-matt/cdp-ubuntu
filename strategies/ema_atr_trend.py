#!/usr/bin/env python3
"""
EMA + ATR Trend-Following Strategy (Long-only)

Core ideas for 5m ETH:
- Trade only long and bias exposure by regime
- Regime = EMA(short) above EMA(long)
- Target high allocation in uptrends; cut to minimal in downtrends
- Use ATR-based trailing stop and EMA(long)-ATR safety exit
- Rebalance only when allocation drift exceeds threshold to reduce churn

Run via: python backtest.py ema_atr_trend
Class name: EmaAtrTrendStrategy
"""

from typing import Dict, Tuple
from dataclasses import dataclass

# Reuse base components from simple_grid
from strategies.simple_grid import TradingStrategy


class EmaAtrTrendStrategy(TradingStrategy):
    def __init__(
        self,
        initial_balance: float = 1000.0,
        fee_rate: float = 0.001,
        short_ema_period: int = 50,
        long_ema_period: int = 200,
        atr_period: int = 14,
        risk_atr_multiple: float = 3.0,
        max_allocation: float = 0.95,
        min_allocation: float = 0.05,
        rebalance_threshold: float = 0.02,  # 2% allocation drift
        max_trade_fraction: float = 0.25,   # cap per trade to 25% of available
    ):
        self.short_ema_period = short_ema_period
        self.long_ema_period = long_ema_period
        self.atr_period = atr_period
        self.risk_atr_multiple = risk_atr_multiple
        self.max_allocation = max_allocation
        self.min_allocation = min_allocation
        self.rebalance_threshold = rebalance_threshold
        self.max_trade_fraction = max_trade_fraction

        # Indicator state
        self._bar_count = 0
        self._ema_short = None
        self._ema_long = None
        self._prev_close = None
        self._atr = None
        self._tr_sma_accumulator = 0.0
        self._highest_close_in_trend = None
        self._in_uptrend = False
        self._last_updated_close_ts = None  # no-op now; kept for clarity

        super().__init__(initial_balance=initial_balance, fee_rate=fee_rate)

    # ---- Indicator helpers ----
    def _wilder_smooth(self, prev_value: float, new_value: float, period: int) -> float:
        if prev_value is None:
            return new_value
        return (prev_value * (period - 1) + new_value) / period

    def _ema_update(self, prev_ema: float, price: float, period: int) -> float:
        k = 2 / (period + 1)
        if prev_ema is None:
            return price
        return price * k + prev_ema * (1 - k)

    def _update_indicators(self, data: Dict):
        close_price = data['close']
        high_price = data['high']
        low_price = data['low']

        # Update EMAs
        self._ema_short = self._ema_update(self._ema_short, close_price, self.short_ema_period)
        self._ema_long = self._ema_update(self._ema_long, close_price, self.long_ema_period)

        # Update ATR (Wilder)
        if self._prev_close is None:
            tr = high_price - low_price
        else:
            tr = max(
                high_price - low_price,
                abs(high_price - self._prev_close),
                abs(low_price - self._prev_close),
            )

        if self._bar_count < self.atr_period:
            # Build initial SMA of TR
            self._tr_sma_accumulator += tr
            if self._bar_count + 1 == self.atr_period:
                self._atr = self._tr_sma_accumulator / self.atr_period
        else:
            self._atr = self._wilder_smooth(self._atr, tr, self.atr_period)

        # Track regime and trailing reference
        if self._ema_short is not None and self._ema_long is not None:
            uptrend_now = self._ema_short > self._ema_long
            if uptrend_now:
                if self._in_uptrend:
                    # continue tracking highest close during uptrend
                    if self._highest_close_in_trend is None:
                        self._highest_close_in_trend = close_price
                    else:
                        self._highest_close_in_trend = max(self._highest_close_in_trend, close_price)
                else:
                    # entering uptrend
                    self._highest_close_in_trend = close_price
            else:
                # reset when exiting uptrend
                self._highest_close_in_trend = None
            self._in_uptrend = uptrend_now

        self._prev_close = close_price
        self._bar_count += 1
        # No timestamp dependency; update every tick

    # ---- Signal logic ----
    def _target_allocation(self) -> float:
        # Prefer high exposure in uptrends, minimal otherwise
        if self._in_uptrend:
            return self.max_allocation
        return self.min_allocation

    def _current_allocation(self, price: float) -> float:
        total_value = self.portfolio.cash + self.portfolio.eth * price
        if total_value <= 0:
            return 0.0
        return (self.portfolio.eth * price) / total_value

    def _needs_rebalance(self, price: float) -> Tuple[bool, float]:
        target = self._target_allocation()
        current = self._current_allocation(price)
        drift = target - current
        return (abs(drift) >= self.rebalance_threshold, drift)

    def _atr_stop_triggered(self, price: float) -> bool:
        if self._atr is None or self._ema_long is None:
            return False
        safety_level = self._ema_long - self._atr  # buffer below long EMA
        if self._highest_close_in_trend is not None:
            trailing_level = self._highest_close_in_trend - self.risk_atr_multiple * self._atr
        else:
            trailing_level = None

        trigger = False
        if trailing_level is not None and price < trailing_level:
            trigger = True
        if price < safety_level:
            trigger = True
        return trigger

    def should_buy(self, current_price: float, data: Dict) -> Tuple[bool, str]:
        self._update_indicators(data=data)
        # Emergency de-risk handled in should_sell; buy targets towards regime allocation
        need, drift = self._needs_rebalance(current_price)
        if need and drift > 0:
            return True, f"Rebalance up towards {self._target_allocation():.0%} (drift {drift:+.2%})"
        return False, "No buy"

    def should_sell(self, current_price: float, data: Dict) -> Tuple[bool, str]:
        self._update_indicators(data=data)
        # Forced de-risk on ATR stop or regime shift down
        if self._atr_stop_triggered(current_price):
            return True, "ATR/EMA safety exit"
        need, drift = self._needs_rebalance(current_price)
        if need and drift < 0:
            return True, f"Rebalance down towards {self._target_allocation():.0%} (drift {drift:+.2%})"
        return False, "Hold"

    def get_trade_amount(self, current_price: float, action: str) -> float:
        # Translate target allocation into concrete trade size
        total_value = self.portfolio.cash + self.portfolio.eth * current_price
        target_value_in_eth = self._target_allocation() * total_value
        current_value_in_eth = self.portfolio.eth * current_price
        delta_value = target_value_in_eth - current_value_in_eth

        if action == 'BUY' and delta_value > 0:
            # Cap by available cash and per-trade fraction
            desired_cash = min(delta_value, self.portfolio.cash)
            desired_cash = min(desired_cash, self.max_trade_fraction * self.portfolio.cash)
            return max(0.0, desired_cash)

        if action == 'SELL' and delta_value < 0:
            # Convert desired value reduction into ETH amount
            desired_reduction_value = min(-delta_value, self.portfolio.eth * current_price)
            desired_reduction_value = min(desired_reduction_value, self.max_trade_fraction * self.portfolio.eth * current_price)
            eth_to_sell = desired_reduction_value / current_price if current_price > 0 else 0.0
            return max(0.0, eth_to_sell)

        return 0.0

    def process_tick(self, timestamp: int, datetime_str: str, price_data: Dict):
        # Override base to avoid initial forced 50% buy
        current_price = price_data['close']

        # Update indicators first
        self._update_indicators(price_data)

        # Evaluate signals
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

        # Update portfolio value
        self.update_portfolio_value(current_price)

