#!/usr/bin/env python3
"""
Enhanced Backtest with Strategy Comparison
Compare buy-and-hold vs. grid trading strategy
"""

import sys
import os
sys.path.append('.')  # Add current directory to path

import pandas as pd
import glob
from strategies.simple_grid import SimpleGridStrategy, StrategyBacktester

def load_all_eth_data():
    """Load all ETH 5-minute data - same as original backtest.py"""
    print("📊 Loading ETH historical data...")
    
    csv_pattern = "histories/eth_5min/*.csv"
    csv_files = glob.glob(csv_pattern)
    
    if not csv_files:
        csv_pattern = "histories/eth_5min_coinbase_*.csv"
        csv_files = glob.glob(csv_pattern)
    
    if not csv_files:
        print("❌ No ETH 5-minute data found!")
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
        return None
    
    # Combine all dataframes
    combined_df = pd.concat(dfs, ignore_index=True)
    combined_df['datetime_obj'] = pd.to_datetime(combined_df['timestamp'], unit='s')
    combined_df = combined_df.sort_values('timestamp').reset_index(drop=True)
    combined_df = combined_df.drop_duplicates(subset=['timestamp']).reset_index(drop=True)
    
    print(f"✅ Loaded {len(combined_df):,} total price records")
    print(f"📅 Date range: {combined_df['datetime'].iloc[0]} to {combined_df['datetime'].iloc[-1]}")
    
    return combined_df

def calculate_hodl_performance(df, investment_amount=1000):
    """Calculate buy-and-hold performance"""
    start_price = df['open'].iloc[0]
    end_price = df['close'].iloc[-1]
    
    eth_purchased = investment_amount / start_price
    final_value = eth_purchased * end_price
    percent_return = (final_value / investment_amount - 1) * 100
    
    return {
        'final_value': final_value,
        'percent_return': percent_return,
        'eth_purchased': eth_purchased
    }

def main():
    """Main comparison function"""
    print("🚀 Strategy Performance Comparison")
    print("=" * 60)
    
    # Load data
    df = load_all_eth_data()
    if df is None:
        return
    
    investment_amount = 1000
    
    # Calculate buy-and-hold performance
    print(f"\n📈 Calculating Buy-and-Hold Performance...")
    hodl_results = calculate_hodl_performance(df, investment_amount)
    
    print(f"💰 Buy-and-Hold Results:")
    print(f"   Initial: ${investment_amount:,.2f}")
    print(f"   Final: ${hodl_results['final_value']:,.2f}")
    print(f"   Return: {hodl_results['percent_return']:.2f}%")
    print(f"   ETH Owned: {hodl_results['eth_purchased']:.6f}")
    
    # Test different grid strategies
    strategies = [
        ("Conservative Grid (2% threshold)", SimpleGridStrategy(
            initial_balance=investment_amount, 
            price_threshold=0.02,  # 2%
            trade_size_percent=0.05  # 5% per trade
        )),
        ("Standard Grid (1% threshold)", SimpleGridStrategy(
            initial_balance=investment_amount,
            price_threshold=0.01,  # 1%
            trade_size_percent=0.10  # 10% per trade
        )),
        ("Aggressive Grid (0.5% threshold)", SimpleGridStrategy(
            initial_balance=investment_amount,
            price_threshold=0.005,  # 0.5%
            trade_size_percent=0.15  # 15% per trade
        ))
    ]
    
    print(f"\n🔄 Testing Grid Strategies...")
    print("=" * 60)
    
    best_strategy = None
    best_performance = hodl_results['percent_return']
    
    for strategy_name, strategy in strategies:
        print(f"\n🎯 Testing: {strategy_name}")
        print("-" * 40)
        
        backtester = StrategyBacktester(strategy)
        results = backtester.compare_with_hodl(df, hodl_results['percent_return'])
        
        if results['total_return'] > best_performance:
            best_performance = results['total_return']
            best_strategy = strategy_name
    
    # Summary
    print(f"\n🏆 FINAL SUMMARY")
    print("=" * 60)
    print(f"💎 Buy-and-Hold: {hodl_results['percent_return']:.2f}% return")
    
    if best_strategy:
        print(f"🎯 Best Strategy: {best_strategy}")
        print(f"📈 Best Return: {best_performance:.2f}%")
        improvement = best_performance - hodl_results['percent_return']
        print(f"⚡ Improvement: {improvement:+.2f}%")
        
        if improvement > 0:
            print(f"🎉 Grid trading can improve returns!")
        else:
            print(f"🤔 Buy-and-hold was better this time")
    else:
        print(f"📊 No strategy beat buy-and-hold")
    
    print(f"\n💡 Notes:")
    print(f"   • Grid strategies work better in volatile/sideways markets")
    print(f"   • Strong trends favor buy-and-hold")
    print(f"   • ETH had a strong upward trend 2021-2025")
    print(f"   • Try different thresholds for different market conditions")

if __name__ == "__main__":
    main()
