#!/usr/bin/env python3
"""
Modular Strategy Backtester
Run any strategy from strategies/ folder via command line.
Usage: python backtest.py simple_grid
"""

import sys
import os
import time
import importlib
import pandas as pd
import glob
from datetime import datetime
from typing import Dict, Any

def load_all_eth_data():
    """Load all ETH 5-minute data from histories folder."""
    print("📊 Loading ETH historical data...")
    
    # Find all ETH 5-minute CSV files
    csv_pattern = "histories/eth_5min/*.csv"
    csv_files = glob.glob(csv_pattern)
    
    if not csv_files:
        # Try the flat structure
        csv_pattern = "histories/eth_5min_coinbase_*.csv"
        csv_files = glob.glob(csv_pattern)
    
    if not csv_files:
        print("❌ No ETH 5-minute data found!")
        print("Expected files like: histories/eth_5min/eth_5min_coinbase_*.csv")
        return None
    
    print(f"📄 Found {len(csv_files)} CSV files")
    
    # Load and combine all data
    dfs = []
    for csv_file in sorted(csv_files):
        try:
            df = pd.read_csv(csv_file)
            dfs.append(df)
        except Exception as e:
            print(f"⚠️  Error loading {csv_file}: {e}")
    
    if not dfs:
        print("❌ No valid CSV files loaded!")
        return None
    
    # Combine all dataframes
    combined_df = pd.concat(dfs, ignore_index=True)
    
    # Convert timestamp to datetime for easier handling
    combined_df['datetime_obj'] = pd.to_datetime(combined_df['timestamp'], unit='s')
    
    # Sort by timestamp to ensure chronological order
    combined_df = combined_df.sort_values('timestamp').reset_index(drop=True)
    
    # Remove any duplicate timestamps
    combined_df = combined_df.drop_duplicates(subset=['timestamp']).reset_index(drop=True)
    
    print(f"✅ Loaded {len(combined_df):,} total price records")
    print(f"📅 Date range: {combined_df['datetime'].iloc[0]} to {combined_df['datetime'].iloc[-1]}")
    
    return combined_df

def calculate_hodl_performance(df: pd.DataFrame, investment_amount: float = 1000) -> Dict:
    """Calculate buy-and-hold performance baseline."""
    start_price = df['open'].iloc[0]
    end_price = df['close'].iloc[-1]
    
    eth_purchased = investment_amount / start_price
    final_value = eth_purchased * end_price
    percent_return = (final_value / investment_amount - 1) * 100
    
    # Calculate time period
    start_dt = pd.to_datetime(df['datetime'].iloc[0])
    end_dt = pd.to_datetime(df['datetime'].iloc[-1])
    days = (end_dt - start_dt).days
    years = days / 365.25
    annualized_return = ((final_value / investment_amount) ** (1/years) - 1) * 100 if years > 0 else 0
    
    return {
        'initial_investment': investment_amount,
        'final_value': final_value,
        'percent_return': percent_return,
        'annualized_return': annualized_return,
        'eth_purchased': eth_purchased,
        'start_price': start_price,
        'end_price': end_price,
        'days': days,
        'years': years
    }

def load_strategy(strategy_name: str):
    """Dynamically load strategy from strategies/ folder."""
    try:
        # Import the strategy module
        module_path = f"strategies.{strategy_name}"
        strategy_module = importlib.import_module(module_path)
        
        # Look for strategy class (convert snake_case to CamelCase)
        class_name = ''.join(word.capitalize() for word in strategy_name.split('_')) + 'Strategy'
        
        if hasattr(strategy_module, class_name):
            strategy_class = getattr(strategy_module, class_name)
            return strategy_class
        else:
            print(f"❌ Strategy class '{class_name}' not found in {module_path}")
            print(f"Available attributes: {[attr for attr in dir(strategy_module) if not attr.startswith('_')]}")
            return None
            
    except ImportError as e:
        print(f"❌ Failed to import strategy '{strategy_name}': {e}")
        print(f"Make sure strategies/{strategy_name}.py exists")
        return None
    except Exception as e:
        print(f"❌ Error loading strategy '{strategy_name}': {e}")
        return None

def run_strategy_backtest(df: pd.DataFrame, strategy_class, investment_amount: float = 1000):
    """Run backtest with CPU-friendly pauses."""
    print(f"🎯 Running {strategy_class.__name__} backtest...")
    print(f"💰 Initial investment: ${investment_amount:,.2f}")
    print(f"📊 Processing {len(df):,} data points with 0.3s pauses between days...")
    
    # Initialize strategy
    strategy = strategy_class(initial_balance=investment_amount)
    
    # Group data by day to add pauses
    df['date'] = pd.to_datetime(df['timestamp'], unit='s').dt.date
    daily_groups = df.groupby('date')
    # Optional limit for quick test runs
    max_days_env = os.getenv('BACKTEST_MAX_DAYS')
    if max_days_env is not None:
        try:
            max_days = int(max_days_env)
            unique_dates = list(daily_groups.groups.keys())[:max_days]
            daily_groups = ((d, df[df['date'] == d]) for d in unique_dates)
            total_days = len(unique_dates)
        except Exception:
            # Fallback to full dataset if env var invalid
            daily_groups = df.groupby('date')
            total_days = daily_groups.ngroups
    else:
        total_days = daily_groups.ngroups
    
    print(f"📅 Processing {total_days:,} days of data...")
    
    start_time = time.time()
    processed_days = 0
    
    for date, day_data in daily_groups:
        # Process each tick in the day first
        for idx, row in day_data.iterrows():
            price_data = {
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume']
            }
            
            strategy.process_tick(
                timestamp=int(row['timestamp']),
                datetime_str=row['datetime'],
                price_data=price_data
            )
        
        processed_days += 1
        
        # Update final portfolio value for the day
        final_price_of_day = day_data.iloc[-1]['close']
        strategy.update_portfolio_value(final_price_of_day)
        current_value = strategy.portfolio.total_value
        
        # Calculate PnL properly - total account value vs initial investment
        if processed_days == 1:
            # Day 1: Show change from initial $1000 investment
            # After buying initial ETH position, we should be close to $1000 (cash + ETH value)
            daily_pnl = current_value - investment_amount
        else:
            # Other days: Compare to previous day's end value
            if len(strategy.portfolio_history) > 0:
                prev_value = strategy.portfolio_history[-1]['total_value']
                daily_pnl = current_value - prev_value
            else:
                daily_pnl = 0
        
        total_pnl = ((current_value / investment_amount) - 1) * 100
        
        # Color coding for PnL
        pnl_color = "🟢" if daily_pnl >= 0 else "🔴"
        total_color = "🟢" if total_pnl >= 0 else "🔴"
        
        print(f"📅 {date} | 💰 ${current_value:,.0f} | {pnl_color} Day: {daily_pnl:+.0f} | {total_color} Total: {total_pnl:+.1f}% | 📊 ETH: ${final_price_of_day:.0f} | 🔄 {strategy.portfolio.trades_count} trades")
        
        # Record end-of-day portfolio state for next day's comparison
        strategy.portfolio_history.append({
            'date': str(date),
            'total_value': current_value,
            'cash': strategy.portfolio.cash,
            'eth': strategy.portfolio.eth,
            'trades_count': strategy.portfolio.trades_count
        })
        
        # Progress milestone every 100 days
        if processed_days % 100 == 0:
            progress = (processed_days / total_days) * 100
            elapsed = time.time() - start_time
            estimated_total = (elapsed / processed_days) * total_days
            remaining = estimated_total - elapsed
            print(f"   🎯 MILESTONE: {progress:.1f}% complete ({processed_days}/{total_days} days) | ⏱️ ETA: {remaining/60:.1f}m | 💎 Portfolio: ${current_value:,.0f}")
        
        # CPU-friendly pause between days (configurable)
        sleep_sec = float(os.getenv('BACKTEST_SLEEP_SEC', '0.15'))
        if sleep_sec > 0:
            time.sleep(sleep_sec)
    
    print(f"✅ Backtest completed in {(time.time() - start_time)/60:.1f} minutes")
    
    # Calculate final results
    final_value = strategy.portfolio.total_value
    total_return = (final_value / investment_amount - 1) * 100
    total_trades = len(strategy.trade_history)
    
    # Calculate max drawdown
    if strategy.portfolio_history:
        portfolio_values = [p['total_value'] for p in strategy.portfolio_history]
        peak = pd.Series(portfolio_values).expanding().max()
        drawdown = (peak - pd.Series(portfolio_values)) / peak
        max_drawdown = drawdown.max() * 100
    else:
        max_drawdown = 0
    
    return {
        'strategy_name': strategy_class.__name__,
        'initial_investment': investment_amount,
        'final_value': final_value,
        'total_return': total_return,
        'total_trades': total_trades,
        'max_drawdown': max_drawdown,
        'final_cash': strategy.portfolio.cash,
        'final_eth': strategy.portfolio.eth,
        'trade_history': strategy.trade_history,
        'portfolio_history': strategy.portfolio_history
    }

def display_results(hodl_results: Dict, strategy_results: Dict):
    """Display comparison results."""
    print(f"\n🏆 BACKTEST RESULTS COMPARISON")
    print("=" * 60)
    
    print(f"💰 Initial Investment: ${hodl_results['initial_investment']:,.2f}")
    print(f"📅 Period: {hodl_results['days']:,} days ({hodl_results['years']:.2f} years)")
    print(f"📈 Start Price: ${hodl_results['start_price']:.2f}")
    print(f"📈 End Price: ${hodl_results['end_price']:.2f}")
    
    print(f"\n📊 PERFORMANCE COMPARISON:")
    print("-" * 60)
    print(f"🔹 Buy & Hold:")
    print(f"   Final Value: ${hodl_results['final_value']:,.2f}")
    print(f"   Total Return: {hodl_results['percent_return']:.2f}%")
    print(f"   Annualized: {hodl_results['annualized_return']:.2f}%")
    print(f"   ETH Owned: {hodl_results['eth_purchased']:.6f}")
    
    print(f"\n🎯 {strategy_results['strategy_name']}:")
    print(f"   Final Value: ${strategy_results['final_value']:,.2f}")
    print(f"   Total Return: {strategy_results['total_return']:.2f}%")
    print(f"   Max Drawdown: {strategy_results['max_drawdown']:.2f}%")
    print(f"   Total Trades: {strategy_results['total_trades']:,}")
    print(f"   Final Cash: ${strategy_results['final_cash']:,.2f}")
    print(f"   Final ETH: {strategy_results['final_eth']:.6f}")
    
    # Calculate outperformance
    outperformance = strategy_results['total_return'] - hodl_results['percent_return']
    
    print(f"\n⚖️  PERFORMANCE ANALYSIS:")
    print("-" * 60)
    print(f"Outperformance: {outperformance:+.2f}%")
    
    if outperformance > 0:
        print(f"🎉 Strategy BEAT buy-and-hold by {outperformance:.2f}%!")
        improvement = (strategy_results['final_value'] - hodl_results['final_value'])
        print(f"💎 Extra profit: ${improvement:+,.2f}")
    else:
        print(f"📉 Strategy UNDERPERFORMED buy-and-hold by {abs(outperformance):.2f}%")
        loss = (hodl_results['final_value'] - strategy_results['final_value'])
        print(f"💸 Opportunity cost: ${loss:,.2f}")
    
    # Risk-adjusted analysis
    if strategy_results['max_drawdown'] > 0:
        risk_adjusted_return = strategy_results['total_return'] / strategy_results['max_drawdown']
        print(f"🎲 Risk-adjusted return: {risk_adjusted_return:.2f}")

def list_available_strategies():
    """List all available strategies in strategies/ folder."""
    strategies_dir = "strategies"
    if not os.path.exists(strategies_dir):
        print(f"❌ No strategies folder found at {strategies_dir}/")
        return []
    
    strategy_files = [f[:-3] for f in os.listdir(strategies_dir) 
                     if f.endswith('.py') and not f.startswith('__')]
    
    if strategy_files:
        print(f"📁 Available strategies in {strategies_dir}/:")
        for strategy in strategy_files:
            print(f"   • {strategy}")
    else:
        print(f"❌ No strategy files found in {strategies_dir}/")
    
    return strategy_files

def main():
    """Main backtesting function."""
    print("🚀 Modular Strategy Backtester")
    print("=" * 50)
    
    # Check command line arguments
    if len(sys.argv) < 2:
        print("❌ Please provide a strategy name!")
        print("\nUsage: python backtest.py <strategy_name>")
        print("\nExample: python backtest.py simple_grid")
        print()
        list_available_strategies()
        sys.exit(1)
    
    strategy_name = sys.argv[1]
    investment_amount = float(sys.argv[2]) if len(sys.argv) > 2 else 1000.0
    
    print(f"🎯 Selected strategy: {strategy_name}")
    print(f"💰 Investment amount: ${investment_amount:,.2f}")
    
    # Load historical data
    df = load_all_eth_data()
    if df is None:
        sys.exit(1)
    
    # Calculate buy-and-hold baseline
    print(f"\n📈 Calculating buy-and-hold baseline...")
    hodl_results = calculate_hodl_performance(df, investment_amount)
    
    # Load strategy
    print(f"\n🔧 Loading strategy: {strategy_name}")
    strategy_class = load_strategy(strategy_name)
    if strategy_class is None:
        print("\n💡 Available strategies:")
        list_available_strategies()
        sys.exit(1)
    
    # Run strategy backtest
    print(f"\n🎮 Running strategy backtest...")
    strategy_results = run_strategy_backtest(df, strategy_class, investment_amount)
    
    # Display results
    display_results(hodl_results, strategy_results)
    
    print(f"\n✅ Backtest completed successfully!")
    print(f"🎯 Strategy: {strategy_name}")
    print(f"📊 Final PnL: {strategy_results['total_return']:+.2f}%")

if __name__ == "__main__":
    main()