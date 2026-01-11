#!/usr/bin/env python3
"""
PROFESSIONAL ARBITRAGE TRADING SYSTEM - MAIN ORCHESTRATOR
Version: 2.0.0
Description: Core orchestration engine for multi-exchange arbitrage trading system
Author: Quantum Trading Systems
"""

import asyncio
import json
import logging
import signal
import sys
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

from data_feed import DataFeed
from market_context import MarketContext, ArbitrageAnalyzer
from order_executor import OrderExecutor
from exchange_wrappers import ExchangeWrapperFactory
from monitoring import SystemMonitor, PerformanceTracker
from utils.helpers import format_currency, calculate_percentage, exponential_backoff
from utils.logger import setup_logger


class SystemOrchestrator:
    """Main orchestrator for the arbitrage trading system."""
    
    def __init__(self, config_path: str = 'config/bot_config.json'):
        """Initialize the orchestrator with configuration."""
        self.config_path = config_path
        self.config = self._load_config()
        self.logger = setup_logger('ArbitrageBot', self.config.get('log_level', 'INFO'))
        
        # System state
        self.running = False
        self.shutdown_requested = False
        self.cycle_count = 0
        self.last_trade_time = None
        self.consecutive_failures = 0
        
        # Performance tracking
        self.performance_tracker = PerformanceTracker()
        
        # Core components (initialized in _initialize_components)
        self.data_feed = None
        self.exchange_wrappers = {}
        self.order_executor = None
        self.market_context = None
        self.arbitrage_analyzer = None
        self.system_monitor = None
        
        # Settings cache
        self.settings = {}
        
        # Signal handling
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.logger.info("✅ Configuration loaded from {}".format(config_path))
        
    def _load_config(self) -> Dict:
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.error(f"❌ Config file not found: {self.config_path}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            self.logger.error(f"❌ Invalid JSON in config file: {e}")
            sys.exit(1)
    
    def _initialize_components(self):
        """Initialize all system components."""
        self.logger.info("🔄 Initializing system components...")
        
        # Initialize settings cache
        self.settings = {
            'position_size': self.config.get('position_size', 500.0),
            'max_position_size': self.config.get('max_position_size', 5000.0),
            'min_position_size_usd': self.config.get('min_position_size_usd', 10.0),
            'min_profit_threshold': self.config.get('min_profit_threshold', 0.5),
            'slippage_tolerance_percent': self.config.get('slippage_tolerance_percent', 0.1),
            'min_stable_per_exchange': self.config.get('min_stable_per_exchange', 1500.0),
            'cycle_delay': self.config.get('cycle_delay', 2.0),
            'max_consecutive_failures': self.config.get('max_consecutive_failures', 5)
        }
        
        # Initialize DataFeed
        self.data_feed = DataFeed(self.config, self.logger)
        
        # Initialize exchange wrappers
        exchange_configs = self.config.get('exchanges', {})
        for exchange_id, exchange_config in exchange_configs.items():
            if exchange_config.get('enabled', False):
                try:
                    wrapper = ExchangeWrapperFactory.create_wrapper(
                        exchange_id, exchange_config, self.logger
                    )
                    self.exchange_wrappers[exchange_id] = wrapper
                    self.logger.info(f"✅ {exchange_id} connected - Pairs: {len(wrapper.symbols)}/{len(exchange_config.get('symbols', []))}")
                except Exception as e:
                    self.logger.error(f"❌ Failed to initialize {exchange_id}: {e}")
        
        if not self.exchange_wrappers:
            self.logger.error("❌ No exchanges initialized. Check configuration.")
            sys.exit(1)
        
        # Initialize Market Context
        self.market_context = MarketContext(self.config, self.logger)
        
        # Initialize Arbitrage Analyzer
        self.arbitrage_analyzer = ArbitrageAnalyzer(
            self.market_context.get_context(),
            self.config,
            self.logger
        )
        
        # Initialize Order Executor
        self.order_executor = OrderExecutor(self.config, self.logger)
        
        # Initialize System Monitor
        self.system_monitor = SystemMonitor(self.config, self.logger)
        
        # Initialize latency mode
        self._initialize_latency_mode()
        
        self.logger.info("✅ All system components initialized successfully")
    
    def _initialize_latency_mode(self):
        """Initialize latency mode based on network conditions."""
        try:
            latency = self.data_feed.measure_network_latency()
            self.logger.info(f"📡 Network latency: {latency:.1f}ms")
            
            if latency > 500:
                self.data_feed.set_latency_mode('HIGH_LATENCY')
                self.logger.info("🔄 HIGH_LATENCY mode activated (REST polling)")
            else:
                self.data_feed.set_latency_mode('LOW_LATENCY')
                self.logger.info("⚡ LOW_LATENCY mode activated (WebSocket streaming)")
                
        except Exception as e:
            self.logger.warning(f"⚠️  Could not measure latency: {e}. Using default mode.")
            self.data_feed.set_latency_mode('LOW_LATENCY')
    
    def _check_sufficient_balances(self):
        """Check exchange balances and determine capital availability mode.
        No longer blocks trading based on a fixed minimum.
        """
        try:
            # Initialize storage for total balance per exchange if it doesn't exist
            if not hasattr(self, '_exchange_total_balances'):
                self._exchange_total_balances = {}
            
            problems = []
            for name, wrapper in self.exchange_wrappers.items():
                # Get BTC balance
                btc_balance = wrapper.free_balances.get('BTC', 0)
                required_btc = 0.001  # Minimum BTC for trading
                
                if btc_balance < required_btc:
                    problems.append({
                        'exchange': name,
                        'currency': 'BTC',
                        'current': btc_balance,
                        'required': required_btc,
                        'deficit': required_btc - btc_balance
                    })
                
                # Check stablecoins with 1% tolerance
                stablecoins = ['USDT', 'USDC', 'USD']
                stable_balance = 0.0
                for coin in stablecoins:
                    stable_balance += wrapper.free_balances.get(coin, 0)
                
                # --- DYNAMIC CAPITAL MODE: Store total balance, never block on stable minimum ---
                # 1. Calculate total balance (USD) for this exchange
                try:
                    total_balance_usd = wrapper.get_total_balance_usd()
                except AttributeError:
                    # Fallback calculation: BTC balance * price + stable balance
                    btc_price = self.data_feed.get_last_price('BTC/USDT')
                    total_balance_usd = stable_balance + (btc_balance * btc_price)
                
                # Store for the mode calculation later in the cycle
                self._exchange_total_balances[name] = total_balance_usd
                
                # 2. Only warn for critically low stable balance (for fees), DO NOT BLOCK
                required_stable_for_fees = 50  # Minimal amount for transaction fees
                if stable_balance < required_stable_for_fees:
                    self.logger.warning(f"⚠️  {name} has low stablecoins (${stable_balance:.2f}) for network fees.")
                # --- END DYNAMIC CAPITAL MODE LOGIC ---
                
                # Check BNB with 5% tolerance (more sensitive)
                fee_token = wrapper.get_fee_token()
                min_fee_token = wrapper.get_min_fee_token_balance()
                if fee_token and min_fee_token > 0:
                    fee_token_balance = wrapper.free_balances.get(fee_token, 0)
                    if fee_token_balance < (min_fee_token * 0.95):
                        problems.append({
                            'exchange': name,
                            'currency': fee_token,
                            'current': fee_token_balance,
                            'required': min_fee_token,
                            'deficit': min_fee_token - fee_token_balance,
                            'details': f"Fee discount token low"
                        })
            
            # Prioritize problems
            if problems:
                # BTC problems first (most critical)
                btc_problems = [p for p in problems if p['currency'] == 'BTC']
                if btc_problems:
                    return btc_problems[0]
                
                # Then BNB (fee discount important)
                fee_token_problems = [p for p in problems if p['currency'] in ['BNB']]
                if fee_token_problems:
                    return fee_token_problems[0]
                
                # Then stablecoins
                return problems[0]
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error in _check_sufficient_balances: {e}")
            return None
    
    def _update_capital_mode(self):
        """Determine capital mode (BOTTLENECKED/BALANCED) and set available_capital_usd."""
        try:
            if not hasattr(self, '_exchange_total_balances'):
                self.capital_mode = "BALANCED"
                self.available_capital_usd = self.settings.get('max_position_size', 5000)
                return
                
            balances = list(self._exchange_total_balances.values())
            min_bal = min(balances)
            max_bal = max(balances)
            
            # BOTTLENECK MODE: Largest balance is > 1.5x the smallest
            if max_bal > (min_bal * 1.5):
                self.capital_mode = "BOTTLENECKED"
                # Use 95% of the smallest (limiting) account's balance
                self.available_capital_usd = min_bal * 0.95
                limiting_exchange = [name for name, bal in self._exchange_total_balances.items() if bal == min_bal][0]
                self.logger.warning(
                    f"🚨 CAPITAL BOTTLENECKED. Limiting account: {limiting_exchange} (${min_bal:.2f}). "
                    f"Available trading capital: ${self.available_capital_usd:.2f}"
                )
            # BALANCED MODE
            else:
                self.capital_mode = "BALANCED"
                # Use 40% of the AVERAGE balance across all accounts
                avg_bal = sum(balances) / len(balances)
                self.available_capital_usd = avg_bal * 0.40
                self.logger.info(
                    f"✅ Capital Balanced. Average balance: ${avg_bal:.2f}. "
                    f"Available trading capital: ${self.available_capital_usd:.2f}"
                )
                
        except Exception as e:
            self.logger.error(f"Error in _update_capital_mode: {e}")
            self.capital_mode = "BALANCED"
            self.available_capital_usd = self.settings.get('max_position_size', 5000)
    
    def _check_connection_health(self) -> bool:
        """Check health of all exchange connections."""
        unhealthy = []
        for name, wrapper in self.exchange_wrappers.items():
            if not wrapper.is_healthy():
                unhealthy.append(name)
        
        if unhealthy:
            self.logger.warning(f"⚠️  Unhealthy connections: {', '.join(unhealthy)}")
            return False
        
        return True
    
    def _fetch_market_data(self) -> Dict:
        """Fetch market data from all exchanges."""
        try:
            symbols = self.config.get('symbols', ['BTC/USDT'])
            price_data = {}
            
            for symbol in symbols:
                symbol_data = {}
                for exchange_id, wrapper in self.exchange_wrappers.items():
                    try:
                        ticker = wrapper.fetch_ticker(symbol)
                        order_book = wrapper.fetch_order_book(symbol, limit=20)
                        
                        symbol_data[exchange_id] = {
                            'bid': ticker['bid'],
                            'ask': ticker['ask'],
                            'last': ticker['last'],
                            'volume': ticker['baseVolume'],
                            'order_book': order_book,
                            'timestamp': time.time()
                        }
                    except Exception as e:
                        self.logger.debug(f"Could not fetch {symbol} from {exchange_id}: {e}")
                        continue
                
                if symbol_data:
                    price_data[symbol] = symbol_data
            
            return price_data
            
        except Exception as e:
            self.logger.error(f"Error fetching market data: {e}")
            return {}
    
    def _analyze_market_conditions(self, price_data: Dict) -> Dict:
        """Analyze overall market conditions."""
        context = {
            'volatility': 'NORMAL',
            'trend': 'NEUTRAL',
            'liquidity': 'NORMAL',
            'spread_conditions': 'NORMAL',
            'market_sentiment': 'NEUTRAL'
        }
        
        try:
            # Calculate volatility
            prices = []
            for symbol_data in price_data.values():
                for exchange_data in symbol_data.values():
                    prices.append(exchange_data['last'])
            
            if len(prices) > 10:
                returns = np.diff(prices) / prices[:-1]
                volatility = np.std(returns) * np.sqrt(365 * 24)  # Annualized
                
                if volatility > 0.8:
                    context['volatility'] = 'HIGH'
                elif volatility < 0.3:
                    context['volatility'] = 'LOW'
            
            # Analyze spreads
            spreads = []
            for symbol, symbol_data in price_data.items():
                for exchange_id, data in symbol_data.items():
                    if data['ask'] > 0 and data['bid'] > 0:
                        spread = (data['ask'] - data['bid']) / data['ask'] * 100
                        spreads.append(spread)
            
            if spreads:
                avg_spread = np.mean(spreads)
                if avg_spread > 0.2:
                    context['spread_conditions'] = 'WIDE'
                elif avg_spread < 0.05:
                    context['spread_conditions'] = 'TIGHT'
            
            # Update market context
            self.market_context.update(context)
            
        except Exception as e:
            self.logger.debug(f"Error in market analysis: {e}")
        
        return context
    
    def find_arbitrage_opportunities(self, price_data, symbols, market_context):
        """Find arbitrage opportunities with market context awareness"""
        opportunities = []
        
        # ==================== PARAMETER CALCULATION ====================
        market_volatility = market_context.get('volatility', 'NORMAL')
        spread_conditions = market_context.get('spread_conditions', 'NORMAL')
        market_sentiment = market_context.get('market_sentiment', 'NEUTRAL')
        
        # Calculate adaptive parameters
        base_min_profit = self.settings['min_profit_threshold']
        base_min_spread = 0.08  # 0.08% base spread
        
        # Volatility adjustment
        if market_volatility == 'HIGH':
            min_profit = base_min_profit * 1.5
            min_spread = base_min_spread * 1.3
            confidence_multiplier = 0.7
        elif market_volatility == 'LOW':
            min_profit = base_min_profit * 0.8
            min_spread = base_min_spread * 0.8
            confidence_multiplier = 1.2
        else:  # NORMAL
            min_profit = base_min_profit
            min_spread = base_min_spread
            confidence_multiplier = 1.0
        
        # Spread condition adjustment
        if spread_conditions == 'WIDE':
            min_spread *= 1.2
            confidence_multiplier *= 0.9
        elif spread_conditions == 'TIGHT':
            min_spread *= 0.8
            confidence_multiplier *= 1.1
        
        # Market sentiment adjustment
        if market_sentiment == 'BEARISH':
            confidence_multiplier *= 0.9
        elif market_sentiment == 'BULLISH':
            confidence_multiplier *= 1.1
        
        # ==================== OPPORTUNITY SCANNING ====================
        for symbol in symbols:
            if symbol not in price_data:
                continue
                
            symbol_data = price_data[symbol]
            exchanges = list(symbol_data.keys())
            
            # Find best buy and sell prices
            for i, buy_exchange in enumerate(exchanges):
                for j, sell_exchange in enumerate(exchanges):
                    if i == j:
                        continue
                    
                    buy_data = symbol_data[buy_exchange]
                    sell_data = symbol_data[sell_exchange]
                    
                    if not buy_data or not sell_data:
                        continue
                    
                    buy_price = buy_data['ask']  # We buy at ask
                    sell_price = sell_data['bid']  # We sell at bid
                    
                    # Calculate spread percentage
                    spread_pct = (sell_price - buy_price) / buy_price * 100
                    
                    if spread_pct < min_spread:
                        continue
                    
                    # Calculate estimated profit
                    # DYNAMIC POSITION SIZE based on capital mode
                    # Ensure mode is updated (call it if not already called in this cycle)
                    if not hasattr(self, 'available_capital_usd'):
                        self._update_capital_mode()
                    
                    # Start with the available capital determined by the mode
                    position_size_usd = self.available_capital_usd
                    
                    # Adjust slightly by confidence if desired (optional)
                    position_size_usd = position_size_usd * (1.0 + (confidence_multiplier * 0.1))  # Max 10% boost
                    
                    # Ensure it respects configured absolute maximum and minimum
                    position_size = min(position_size_usd, self.settings['max_position_size'])
                    position_size = max(position_size, self.settings.get('min_position_size_usd', 10.0))
                    
                    self.logger.debug(
                        f"   📊 Trading params: Mode={self.capital_mode}, "
                        f"Size=${position_size:.0f} (from ${self.available_capital_usd:.0f}), "
                        f"Confidence={confidence_multiplier:.2f}"
                    )
                    
                    # Calculate fees
                    buy_fee_rate = self.exchange_wrappers[buy_exchange].get_taker_fee()
                    sell_fee_rate = self.exchange_wrappers[sell_exchange].get_taker_fee()
                    
                    # Calculate profit after fees
                    gross_profit = (sell_price - buy_price) * (position_size / buy_price)
                    fees = (buy_price * buy_fee_rate + sell_price * sell_fee_rate) * (position_size / buy_price)
                    net_profit = gross_profit - fees
                    
                    if net_profit < min_profit:
                        continue
                    
                    # Calculate confidence score
                    confidence = self._calculate_confidence(
                        buy_data, sell_data, spread_pct, market_context
                    ) * confidence_multiplier
                    
                    # Check liquidity
                    buy_liquidity = self._check_liquidity(buy_data['order_book'], position_size / buy_price)
                    sell_liquidity = self._check_liquidity(sell_data['order_book'], position_size / buy_price)
                    
                    if not buy_liquidity or not sell_liquidity:
                        continue
                    
                    # Add slippage estimate
                    buy_slippage = self._estimate_slippage(buy_data['order_book'], position_size / buy_price, 'buy')
                    sell_slippage = self._estimate_slippage(sell_data['order_book'], position_size / buy_price, 'sell')
                    
                    adjusted_buy_price = buy_price * (1 + buy_slippage)
                    adjusted_sell_price = sell_price * (1 - sell_slippage)
                    
                    # Recalculate profit with slippage
                    adjusted_gross_profit = (adjusted_sell_price - adjusted_buy_price) * (position_size / adjusted_buy_price)
                    adjusted_fees = (adjusted_buy_price * buy_fee_rate + adjusted_sell_price * sell_fee_rate) * (position_size / adjusted_buy_price)
                    adjusted_net_profit = adjusted_gross_profit - adjusted_fees
                    
                    # Final check with slippage
                    if adjusted_net_profit < min_profit:
                        continue
                    
                    # Create opportunity object
                    opportunity = {
                        'symbol': symbol,
                        'buy_exchange': buy_exchange,
                        'sell_exchange': sell_exchange,
                        'buy_price': buy_price,
                        'sell_price': sell_price,
                        'adjusted_buy_price': adjusted_buy_price,
                        'adjusted_sell_price': adjusted_sell_price,
                        'spread_pct': spread_pct,
                        'position_size': position_size,
                        'estimated_profit': net_profit,
                        'adjusted_profit': adjusted_net_profit,
                        'confidence': min(confidence, 1.0),  # Cap at 1.0
                        'timestamp': time.time(),
                        'buy_liquidity_ok': buy_liquidity,
                        'sell_liquidity_ok': sell_liquidity,
                        'buy_slippage_pct': buy_slippage * 100,
                        'sell_slippage_pct': sell_slippage * 100,
                        'market_context': market_context.copy()
                    }
                    
                    opportunities.append(opportunity)
        
        # Sort by adjusted profit
        opportunities.sort(key=lambda x: x['adjusted_profit'], reverse=True)
        
        return opportunities[:5]  # Return top 5 opportunities
    
    def _calculate_confidence(self, buy_data, sell_data, spread_pct, market_context):
        """Calculate confidence score for an arbitrage opportunity."""
        confidence = 0.5  # Base confidence
        
        # Spread-based confidence
        if spread_pct > 0.15:
            confidence += 0.2
        elif spread_pct > 0.10:
            confidence += 0.1
        
        # Volume-based confidence
        buy_volume = buy_data.get('volume', 0)
        sell_volume = sell_data.get('volume', 0)
        
        if buy_volume > 100 and sell_volume > 100:
            confidence += 0.1
        elif buy_volume > 50 and sell_volume > 50:
            confidence += 0.05
        
        # Order book depth confidence
        buy_depth = self._calculate_order_book_depth(buy_data['order_book'])
        sell_depth = self._calculate_order_book_depth(sell_data['order_book'])
        
        if buy_depth > 10 and sell_depth > 10:
            confidence += 0.1
        elif buy_depth > 5 and sell_depth > 5:
            confidence += 0.05
        
        # Market context adjustment
        volatility = market_context.get('volatility', 'NORMAL')
        if volatility == 'LOW':
            confidence += 0.1
        elif volatility == 'HIGH':
            confidence -= 0.1
        
        return min(max(confidence, 0.1), 0.95)  # Keep within bounds
    
    def _calculate_order_book_depth(self, order_book, depth_percent=0.5):
        """Calculate order book depth within given percentage of mid price."""
        if not order_book or 'bids' not in order_book or 'asks' not in order_book:
            return 0
        
        bids = order_book['bids']
        asks = order_book['asks']
        
        if not bids or not asks:
            return 0
        
        best_bid = bids[0][0]
        best_ask = asks[0][0]
        mid_price = (best_bid + best_ask) / 2
        
        price_range_low = mid_price * (1 - depth_percent / 100)
        price_range_high = mid_price * (1 + depth_percent / 100)
        
        bid_depth = sum(amount for price, amount in bids if price >= price_range_low)
        ask_depth = sum(amount for price, amount in asks if price <= price_range_high)
        
        return min(bid_depth, ask_depth)
    
    def _check_liquidity(self, order_book, required_amount):
        """Check if order book has sufficient liquidity for required amount."""
        if not order_book or 'bids' not in order_book or 'asks' not in order_book:
            return False
        
        bids = order_book['bids']
        asks = order_book['asks']
        
        if not bids or not asks:
            return False
        
        # Check ask side (for buying)
        ask_liquidity = 0
        for price, amount in asks:
            ask_liquidity += amount
            if ask_liquidity >= required_amount:
                break
        
        # Check bid side (for selling)
        bid_liquidity = 0
        for price, amount in bids:
            bid_liquidity += amount
            if bid_liquidity >= required_amount:
                break
        
        return ask_liquidity >= required_amount and bid_liquidity >= required_amount
    
    def _estimate_slippage(self, order_book, amount, side):
        """Estimate slippage for given amount and side."""
        if not order_book:
            return 0.001  # Default 0.1% slippage
        
        if side == 'buy':
            levels = order_book.get('asks', [])
        else:
            levels = order_book.get('bids', [])
        
        if not levels:
            return 0.001
        
        filled = 0
        total_cost = 0
        remaining = amount
        
        for price, level_amount in levels:
            fill_amount = min(remaining, level_amount)
            total_cost += fill_amount * price
            filled += fill_amount
            remaining -= fill_amount
            
            if remaining <= 0:
                break
        
        if filled == 0:
            return 0.001
        
        avg_price = total_cost / filled
        first_price = levels[0][0]
        
        if side == 'buy':
            slippage = (avg_price - first_price) / first_price
        else:
            slippage = (first_price - avg_price) / first_price
        
        return max(slippage, 0)
    
    def _select_best_opportunity(self, opportunities):
        """Select the best opportunity from the list."""
        if not opportunities:
            return None
        
        # Filter by minimum confidence
        min_confidence = 0.6
        filtered = [opp for opp in opportunities if opp['confidence'] >= min_confidence]
        
        if not filtered:
            return None
        
        # Score opportunities
        scored_opportunities = []
        for opp in filtered:
            score = 0
            
            # Profit score (40% weight)
            profit_score = min(opp['adjusted_profit'] / 10, 1.0) * 40
            score += profit_score
            
            # Confidence score (30% weight)
            confidence_score = opp['confidence'] * 30
            score += confidence_score
            
            # Liquidity score (20% weight)
            liquidity_score = 20 if (opp['buy_liquidity_ok'] and opp['sell_liquidity_ok']) else 0
            score += liquidity_score
            
            # Slippage score (10% weight)
            slippage_penalty = (opp['buy_slippage_pct'] + opp['sell_slippage_pct']) / 2
            slippage_score = max(0, 10 - (slippage_penalty * 10))
            score += slippage_score
            
            scored_opportunities.append((score, opp))
        
        # Select highest score
        scored_opportunities.sort(key=lambda x: x[0], reverse=True)
        
        return scored_opportunities[0][1] if scored_opportunities else None
    
    def _execute_trade_cycle(self):
        """Execute a single trade cycle."""
        try:
            self.cycle_count += 1
            
            # Update capital mode at the start of each cycle
            self._update_capital_mode()
            
            # Check connection health
            if not self._check_connection_health():
                self.consecutive_failures += 1
                if self.consecutive_failures >= self.settings['max_consecutive_failures']:
                    self.logger.error("🚨 Too many consecutive failures. Pausing system.")
                    time.sleep(60)
                    self.consecutive_failures = 0
                return
            
            self.consecutive_failures = 0
            
            # Check balances - now only warns, never blocks
            balance_problem = self._check_sufficient_balances()
            if balance_problem:
                self.logger.warning(f"⚠️  Balance issue detected: {balance_problem}")
                # Continue anyway - don't block trading
            
            # Fetch market data
            price_data = self._fetch_market_data()
            if not price_data:
                self.logger.warning("⚠️  No market data available")
                return
            
            # Analyze market conditions
            market_context = self._analyze_market_conditions(price_data)
            
            # Find arbitrage opportunities
            symbols = self.config.get('symbols', ['BTC/USDT'])
            opportunities = self.find_arbitrage_opportunities(
                price_data, symbols, market_context
            )
            
            if not opportunities:
                if self.cycle_count % 50 == 0:
                    self.logger.info("🔍 No arbitrage opportunities found")
                return
            
            # Select best opportunity
            best_opportunity = self._select_best_opportunity(opportunities)
            
            if not best_opportunity:
                return
            
            # Log opportunity
            self.logger.info(
                f"🎯 Opportunity found: {best_opportunity['symbol']} | "
                f"Buy: {best_opportunity['buy_exchange']} @ ${best_opportunity['buy_price']:.2f} | "
                f"Sell: {best_opportunity['sell_exchange']} @ ${best_opportunity['sell_price']:.2f} | "
                f"Spread: {best_opportunity['spread_pct']:.3f}% | "
                f"Est. Profit: ${best_opportunity['adjusted_profit']:.2f} | "
                f"Confidence: {best_opportunity['confidence']:.2f}"
            )
            
            # Execute trade
            success = self.order_executor.execute_arbitrage(
                buy_exchange=best_opportunity['buy_exchange'],
                sell_exchange=best_opportunity['sell_exchange'],
                buy_price=best_opportunity['buy_price'],
                sell_price=best_opportunity['sell_price'],
                symbol=best_opportunity['symbol'],
                position_size=best_opportunity['position_size'],
                expected_profit=best_opportunity['adjusted_profit']
            )
            
            if success:
                self.last_trade_time = time.time()
                self.performance_tracker.record_trade(success)
                self.logger.info(f"✅ Trade executed successfully")
            else:
                self.performance_tracker.record_trade(success)
                self.logger.warning(f"⚠️  Trade execution failed")
            
            # Update system monitor
            self.system_monitor.update_metrics({
                'cycle_count': self.cycle_count,
                'opportunities_found': len(opportunities),
                'trade_executed': success,
                'estimated_profit': best_opportunity['adjusted_profit'] if success else 0
            })
            
        except Exception as e:
            self.logger.error(f"❌ Error in trade cycle: {e}")
            self.logger.debug(traceback.format_exc())
            self.consecutive_failures += 1
    
    def run(self):
        """Main system run loop."""
        try:
            self._initialize_components()
            self.running = True
            
            # Log system startup
            self._log_system_startup()
            
            self.logger.info("🚀 Starting arbitrage trading system...")
            
            # Main loop
            while self.running and not self.shutdown_requested:
                cycle_start = time.time()
                
                # Execute trade cycle
                self._execute_trade_cycle()
                
                # Calculate cycle time and sleep
                cycle_time = time.time() - cycle_start
                sleep_time = max(0.1, self.settings['cycle_delay'] - cycle_time)
                
                if self.cycle_count % 100 == 0:
                    self._log_system_status()
                
                # Check for shutdown during sleep
                for _ in range(int(sleep_time * 10)):
                    if self.shutdown_requested:
                        break
                    time.sleep(0.1)
                
                # Emergency shutdown check
                if self.consecutive_failures >= self.settings['max_consecutive_failures'] * 2:
                    self.logger.critical("🚨 EMERGENCY SHUTDOWN: Too many consecutive failures")
                    self.shutdown_requested = True
            
            self.logger.info("🛑 Trading system stopped")
            
        except KeyboardInterrupt:
            self.logger.info("👋 Received keyboard interrupt")
        except Exception as e:
            self.logger.error(f"❌ Fatal error in main loop: {e}")
            self.logger.debug(traceback.format_exc())
        finally:
            self.shutdown()
    
    def _log_system_startup(self):
        """Log system startup information."""
        self.logger.info("=" * 70)
        self.logger.info("🚀 PROFESSIONAL ARBITRAGE TRADING SYSTEM")
        self.logger.info(f"   System ID: {self.config.get('system_id', 'UNKNOWN')}")
        self.logger.info(f"   Version: {self.config.get('version', '2.0.0')}")
        self.logger.info(f"   Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"   PID: {os.getpid()}")
        self.logger.info(f"   Platform: {platform.platform()}")
        self.logger.info("-" * 70)
        self.logger.info("📊 SYSTEM CONFIGURATION:")
        self.logger.info(f"   Mode: {self.data_feed.latency_mode if self.data_feed else 'UNKNOWN'}")
        self.logger.info(f"   Exchanges: {len(self.exchange_wrappers)} connected")
        self.logger.info(f"   Position Size: ${self.settings['position_size']}")
        self.logger.info(f"   Min Profit/Trade: ${self.settings['min_profit_threshold']}")
        self.logger.info(f"   Cycle Delay: {self.settings['cycle_delay']}s")
        self.logger.info("=" * 70)
    
    def _log_system_status(self):
        """Log periodic system status."""
        try:
            # Get performance metrics
            metrics = self.performance_tracker.get_metrics()
            
            self.logger.info("📈 System Metrics: " +
                f"Cycles: {self.cycle_count} | " +
                f"Trades: {metrics['total_trades']} | " +
                f"Profit: ${metrics['total_profit']:.2f} | " +
                f"Win Rate: {metrics['win_rate']:.1f}% | " +
                f"API Success: {self.system_monitor.get_api_success_rate():.1f}%")
            
            # Log capital mode status
            if hasattr(self, 'capital_mode'):
                self.logger.info(f"💰 Capital Mode: {self.capital_mode} | Available: ${self.available_capital_usd:.2f}")
            
            # Log exchange balances
            if hasattr(self, '_exchange_total_balances'):
                for exchange, balance in self._exchange_total_balances.items():
                    self.logger.debug(f"   {exchange}: ${balance:.2f}")
            
        except Exception as e:
            self.logger.debug(f"Error logging system status: {e}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.warning(f"🚨 Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
    
    def shutdown(self):
        """Gracefully shutdown the system."""
        self.logger.info("🛑 Initiating graceful system shutdown...")
        self.running = False
        
        # Stop data feed
        if self.data_feed:
            self.data_feed.stop()
            self.logger.info("✅ Data feed stopped")
        
        # Log final metrics
        self._log_system_status()
        
        # Log session summary
        self._log_session_summary()
        
        self.logger.info("👋 System shutdown complete. Goodbye!")
    
    def _log_session_summary(self):
        """Log session summary."""
        metrics = self.performance_tracker.get_metrics()
        runtime = time.time() - self.start_time if hasattr(self, 'start_time') else 0
        
        self.logger.info("=" * 70)
        self.logger.info("📊 SESSION SUMMARY:")
        self.logger.info(f"   Duration: {runtime / 3600:.2f} hours")
        self.logger.info(f"   Total Cycles: {self.cycle_count}")
        self.logger.info(f"   Total Trades: {metrics['total_trades']}")
        self.logger.info(f"   Total Profit: ${metrics['total_profit']:.2f}")
        self.logger.info(f"   Total Loss: ${metrics['total_loss']:.2f}")
        self.logger.info(f"   Net P&L: ${metrics['net_pnl']:.2f}")
        self.logger.info(f"   Win Rate: {metrics['win_rate']:.1f}%")
        self.logger.info(f"   Hourly Rate: ${metrics['hourly_rate']:.2f}/hour")
        self.logger.info(f"   Avg Trade Time: {metrics['avg_trade_time']:.1f}ms")
        self.logger.info("=" * 70)



# ==================== MAIN EXECUTION ====================
if __name__ == "__main__":
    # Create config directory if it doesn't exist
    os.makedirs('config', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    # Initialize and run the bot
    bot = ArbitrageBot()
    bot.run()