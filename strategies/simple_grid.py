#!/usr/bin/env python3
"""
Simple Grid Trading Strategy
A modular implementation that trades on price movements.

Strategy Logic:
- Start with 50% cash, 50% ETH
- Buy ETH when price drops >threshold% from last trade
- Sell ETH when price rises >threshold% from last trade
- Use percentage-based position sizing
"""

import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class TradeAction:
    """Represents a trading action"""
    timestamp: int
    datetime: str
    action: str  # 'BUY', 'SELL', 'HOLD'
    price: float
    eth_amount: float
    cash_amount: float
    reason: str

@dataclass
class PortfolioState:
    """Current portfolio state"""
    cash: float
    eth: float
    last_trade_price: float
    total_value: float
    trades_count: int

class TradingStrategy(ABC):
    """Base class for all trading strategies - makes them easily swappable"""
    
    def __init__(self, initial_balance: float = 1000.0, fee_rate: float = 0.001):
        self.initial_balance = initial_balance
        self.fee_rate = fee_rate  # 0.1% trading fee
        self.reset()
    
    def reset(self):
        """Reset strategy to initial state"""
        self.portfolio = PortfolioState(
            cash=self.initial_balance,  # Start with FULL cash amount
            eth=0.0,
            last_trade_price=0.0,
            total_value=self.initial_balance,  # Start with full initial balance
            trades_count=0
        )
        self.trade_history: List[TradeAction] = []
        self.portfolio_history: List[Dict] = []
    
    @abstractmethod
    def should_buy(self, current_price: float, data: Dict) -> Tuple[bool, str]:
        """Return (should_buy, reason)"""
        pass
    
    @abstractmethod
    def should_sell(self, current_price: float, data: Dict) -> Tuple[bool, str]:
        """Return (should_sell, reason)"""
        pass
    
    @abstractmethod
    def get_trade_amount(self, current_price: float, action: str) -> float:
        """Get amount to trade (in USD for buys, in ETH for sells)"""
        pass
    
    def execute_trade(self, timestamp: int, datetime_str: str, price: float, action: str, amount: float, reason: str):
        """Execute a trade and update portfolio"""
        if action == 'BUY' and amount > 0:
            # Buy ETH with cash
            cost = amount  # Amount is in USD
            fee = cost * self.fee_rate
            total_cost = cost + fee
            
            if total_cost <= self.portfolio.cash:
                eth_purchased = cost / price
                self.portfolio.cash -= total_cost
                self.portfolio.eth += eth_purchased
                self.portfolio.last_trade_price = price
                self.portfolio.trades_count += 1
                
                self.trade_history.append(TradeAction(
                    timestamp=timestamp,
                    datetime=datetime_str,
                    action='BUY',
                    price=price,
                    eth_amount=eth_purchased,
                    cash_amount=-total_cost,
                    reason=reason
                ))
                pass  # Trade executed successfully
            else:
                pass  # Trade failed - insufficient funds
        
        elif action == 'SELL' and amount > 0:
            # Sell ETH for cash
            if amount <= self.portfolio.eth:
                revenue = amount * price
                fee = revenue * self.fee_rate
                net_revenue = revenue - fee
                
                self.portfolio.cash += net_revenue
                self.portfolio.eth -= amount
                self.portfolio.last_trade_price = price
                self.portfolio.trades_count += 1
                
                self.trade_history.append(TradeAction(
                    timestamp=timestamp,
                    datetime=datetime_str,
                    action='SELL',
                    price=price,
                    eth_amount=-amount,
                    cash_amount=net_revenue,
                    reason=reason
                ))
                pass  # Trade executed successfully
            else:
                pass  # Trade failed - insufficient ETH
    
    def update_portfolio_value(self, current_price: float):
        """Update total portfolio value"""
        self.portfolio.total_value = self.portfolio.cash + (self.portfolio.eth * current_price)
    
    def process_tick(self, timestamp: int, datetime_str: str, price_data: Dict):
        """Process a single price tick"""
        current_price = price_data['close']
        
        # Initialize on first tick
        if self.portfolio.last_trade_price == 0:
            # Buy initial ETH position (50% of total balance)
            # We start with $1000 cash, buy $500 worth of ETH (minus small buffer for fees)
            initial_eth_investment = self.initial_balance * 0.5 - 5  # $495 (leave $5 buffer for fees)
            self.execute_trade(
                timestamp, datetime_str, current_price, 'BUY', 
                initial_eth_investment, "Initial 50% ETH position"
            )
        
        # Check for buy/sell signals
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
        
        # Always record end-of-day portfolio state for daily PnL calculation
        # This gets called on the last tick of each day

class SimpleGridStrategy(TradingStrategy):
    """
    Simple Grid Trading Strategy
    - Buy when price drops >threshold% from last trade
    - Sell when price rises >threshold% from last trade
    """
    
    def __init__(self, initial_balance: float = 1000.0, 
                 price_threshold: float = 0.01,  # 1% threshold
                 trade_size_percent: float = 0.1,  # Trade 10% of available balance
                 fee_rate: float = 0.001):
        self.price_threshold = price_threshold
        self.trade_size_percent = trade_size_percent
        super().__init__(initial_balance, fee_rate)
    
    def should_buy(self, current_price: float, data: Dict) -> Tuple[bool, str]:
        """Buy when price drops >threshold% from last trade and we have cash"""
        if self.portfolio.cash < 50:  # Need at least $50 to trade
            return False, "Insufficient cash"
        
        if self.portfolio.last_trade_price == 0:
            return False, "No reference price"
        
        price_drop = (self.portfolio.last_trade_price - current_price) / self.portfolio.last_trade_price
        
        if price_drop >= self.price_threshold:
            return True, f"Price dropped {price_drop:.2%} from last trade"
        
        return False, "No buy signal"
    
    def should_sell(self, current_price: float, data: Dict) -> Tuple[bool, str]:
        """Sell when price rises >threshold% from last trade and we have ETH"""
        if self.portfolio.eth < 0.001:  # Need at least 0.001 ETH to trade
            return False, "Insufficient ETH"
        
        if self.portfolio.last_trade_price == 0:
            return False, "No reference price"
        
        price_gain = (current_price - self.portfolio.last_trade_price) / self.portfolio.last_trade_price
        
        if price_gain >= self.price_threshold:
            return True, f"Price gained {price_gain:.2%} from last trade"
        
        return False, "No sell signal"
    
    def get_trade_amount(self, current_price: float, action: str) -> float:
        """Get amount to trade based on available balance"""
        if action == 'BUY':
            # Trade percentage of available cash, but account for fees
            max_trade = self.portfolio.cash - 10  # Keep $10 buffer
            trade_amount = max_trade * self.trade_size_percent
            return max(0, min(trade_amount, max_trade))
        elif action == 'SELL':
            # Trade percentage of available ETH
            trade_amount = self.portfolio.eth * self.trade_size_percent  
            return max(0, min(trade_amount, self.portfolio.eth - 0.001))  # Keep 0.001 ETH buffer
        return 0.0

# Additional strategy variants for testing
class AggressiveGridStrategy(SimpleGridStrategy):
    """More aggressive grid with smaller thresholds and larger trades"""
    
    def __init__(self, initial_balance: float = 1000.0):
        super().__init__(
            initial_balance=initial_balance,
            price_threshold=0.005,  # 0.5% threshold
            trade_size_percent=0.15,  # 15% per trade
            fee_rate=0.001
        )

class ConservativeGridStrategy(SimpleGridStrategy):
    """More conservative grid with larger thresholds and smaller trades"""
    
    def __init__(self, initial_balance: float = 1000.0):
        super().__init__(
            initial_balance=initial_balance,
            price_threshold=0.02,  # 2% threshold
            trade_size_percent=0.05,  # 5% per trade
            fee_rate=0.001
        )

def main():
    """Example usage of the grid strategy"""
    print("🎯 Simple Grid Strategy")
    print("=" * 40)
    print("This strategy can be run via:")
    print("python backtest.py simple_grid")
    print("python backtest.py aggressive_grid")
    print("python backtest.py conservative_grid")
    
    print(f"\n🔧 Strategy Parameters (SimpleGridStrategy):")
    print(f"   📈 Price Threshold: 1% (configurable)")
    print(f"   💰 Trade Size: 10% of available balance (configurable)")
    print(f"   💸 Trading Fee: 0.1% per trade (configurable)")
    print(f"   ⚖️  Initial Split: 50% cash, 50% ETH")

if __name__ == "__main__":
    main()