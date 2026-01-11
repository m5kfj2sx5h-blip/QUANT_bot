#!/usr/bin/env python3
"""
Real-time Status Panel for Arbitrage Bot
Run this in a separate terminal window to see bot activity.
"""

import json
import time
import os
from datetime import datetime

LOG_FILE = '/Users/dj3bosmacbookpro/Desktop/QUANT_bot/bot_logs.txt'
FEE_STATE = '/Users/dj3bosmacbookpro/Desktop/QUANT_bot/fee_state.json'

def tail_log(lines=20):
    """Read last lines of log file"""
    try:
        with open(LOG_FILE, 'r') as f:
            all_lines = f.readlines()
            return ''.join(all_lines[-lines:])
    except:
        return "Log file not found yet..."

def get_fee_credits():
    """Read current fee credits"""
    try:
        with open(FEE_STATE, 'r') as f:
            data = json.load(f)
            kraken = data['exchanges']['kraken']['credit_remaining_usd']
            coinbase = data['exchanges']['coinbase']['credit_remaining_usd']
            return kraken, coinbase
    except:
        return 10000.0, 500.0

def display_status():
    """Show status panel"""
    os.system('clear' if os.name == 'posix' else 'cls')
    
    # Get current time
    now = datetime.now()
    
    print("╔══════════════════════════════════════════════════════╗")
    print("║               ARBITRAGE BOT STATUS PANEL             ║")
    print("╠══════════════════════════════════════════════════════╣")
    print(f"║  Time: {now.strftime('%H:%M:%S')}                                 ║")
    print(f"║  Date: {now.strftime('%Y-%m-%d')}                                 ║")
    print("╠══════════════════════════════════════════════════════╣")
    print("║  STATUS:  WAITING FOR PROFITABLE OPPORTUNITIES       ║")
    print("║  MODE:    BTC/USD/USDT/USDC TRIANGULAR               ║")
    print("╠══════════════════════════════════════════════════════╣")
    
    # Fee credits
    kraken_credit, coinbase_credit = get_fee_credits()
    print(f"║  FEE CREDITS:                                        ║")
    print(f"║    • Kraken:  ${kraken_credit:>7.2f} / $10,000           ║")
    print(f"║    • Coinbase: ${coinbase_credit:>6.2f} / $500             ║")
    print("╠══════════════════════════════════════════════════════╣")
    print("║  LAST LOG ENTRIES:                                   ║")
    print("╠══════════════════════════════════════════════════════╣")
    
    # Show recent logs
    logs = tail_log(10)
    for line in logs.split('\n'):
        if line.strip():
            # Truncate long lines for display
            display_line = line[:58] + "..." if len(line) > 58 else line
            print(f"║  {display_line:<56} ║")
    
    print("╠══════════════════════════════════════════════════════╣")
    print("║  INSTRUCTIONS:                                       ║")
    print("║  • This panel shows real-time activity               ║")
    print("║  • Bot is scanning for price differences             ║")
    print("║  • Trades execute automatically                      ║")
    print("║  • Check logs for trade details                      ║")
    print("╚══════════════════════════════════════════════════════╝")

def main():
    """Main loop"""
    print("Starting status panel... (Ctrl+C to exit)")
    time.sleep(2)
    
    try:
        while True:
            display_status()
            time.sleep(5)  # Update every 5 seconds
    except KeyboardInterrupt:
        print("\nStatus panel stopped.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()