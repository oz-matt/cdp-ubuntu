#!/usr/bin/env python3
"""
Buy and Hold Strategy (for baseline comparison within the same framework)

Executes one initial buy with nearly full allocation and then holds.

Run via: python backtest.py buy_and_hold
Class name: BuyAndHoldStrategy
"""

from typing import Dict, Tuple

from strategies.simple_grid import TradingStrategy


class BuyAndHoldStrategy(TradingStrategy):
    def __init__(self, initial_balance: float = 1000.0, fee_rate: float = 0.001):
        super().__init__(initial_balance=initial_balance, fee_rate=fee_rate)
        self._initialized = False

    def should_buy(self, current_price: float, data: Dict) -> Tuple[bool, str]:
        if not self._initialized and self.portfolio.cash > 0:
            return True, "Initial full allocation"
        return False, "Already allocated"

    def should_sell(self, current_price: float, data: Dict) -> Tuple[bool, str]:
        return False, "Never sell"

    def get_trade_amount(self, current_price: float, action: str) -> float:
        if action == 'BUY' and not self._initialized:
            # Keep small buffer for fees
            amount = max(0.0, self.portfolio.cash - 1.0)
            self._initialized = True
            return amount
        return 0.0

