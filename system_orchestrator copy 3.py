#!/usr/bin/env python3
"""
PROFESSIONAL ARBITRAGE TRADING SYSTEM - MAIN ORCHESTRATOR
Version: 2.0.0 | Architecture: Microservices Integration
Author: Quant Trading System | Last Updated: 2026-01-10

This is the central nervous system that integrates all sophisticated components:
1. Market Microstructure Analysis
2. Auction Theory Implementation
3. Health & Performance Monitoring
4. Dynamic Parameter Adjustment
5. Multi-Exchange Coordination
6. Graceful Degradation Systems
"""

import asyncio
import ccxt
import time
import os
import sys
import signal
import subprocess
import platform
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from dotenv import load_dotenv
import json

# ==================== CORE TRADING COMPONENTS ====================
from data_feed import RESTPollingFeed, WebSocketFeed
from rebalance_monitor import RebalanceMonitor
from order_executor import LowLatencyExecutor, HighLatencyExecutor

# ==================== MARKET INTELLIGENCE MODULES ====================
from auction_context_module import AuctionContextModule
from market_context import MarketContext, AuctionState, MarketPhase, MacroSignal
from health_monitor import HealthMonitor
from data_hub import DataHub

# ==================== LOGGING CONFIGURATION ====================
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

class LogLevel(Enum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

@dataclass
class SystemMetrics:
    """Comprehensive system performance tracking"""
    cycle_count: int = 0
    total_trades: int = 0
    total_profit: float = 0.0
    total_loss: float = 0.0
    win_rate: float = 0.0
    avg_trade_time_ms: float = 0.0
    api_success_rate: float = 1.0
    uptime_seconds: float = 0.0
    memory_usage_mb: float = 0.0
    last_system_check: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict:
        return {
            'cycle_count': self.cycle_count,
            'total_trades': self.total_trades,
            'total_profit': round(self.total_profit, 2),
            'total_loss': round(self.total_loss, 2),
            'win_rate': round(self.win_rate, 3),
            'avg_trade_time_ms': round(self.avg_trade_time_ms, 2),
            'api_success_rate': round(self.api_success_rate, 3),
            'uptime_hours': round(self.uptime_seconds / 3600, 2),
            'memory_usage_mb': round(self.memory_usage_mb, 1)
        }

class ArbitrageBot:
    """
    PROFESSIONAL TRADING BOT - MAIN CONTROLLER
    
    Features:
    - Multi-exchange arbitrage with market microstructure awareness
    - Dynamic parameter adjustment based on auction theory
    - Comprehensive health monitoring and self-healing
    - Graceful degradation and failover systems
    - Performance metrics and telemetry
    - Configurable trading strategies
    """
    
    def __init__(self, config_path: str = 'config/bot_config.json'):
        """Initialize all system components with proper error handling"""
        self.start_time = time.time()
        self.system_id = f"ARB_{int(time.time())}_{os.getpid()}"
        self.config_path = config_path
        
        # Initialize logging FIRST
        self.setup_enterprise_logging()
        
        # Load configuration
        self.config = self.load_configuration()
        
        # Initialize system state
        self.system_metrics = SystemMetrics()
        self.is_shutting_down = False
        self.last_heartbeat = time.time()
        
        # Register signal handlers for graceful shutdown
        self.register_signal_handlers()
        
        # Load environment variables
        load_dotenv()
        
        # Initialize core settings with validation
        self.settings = self.initialize_settings()
        
        # Initialize all components
        self.initialize_components()
        
        # Log system initialization
        self.log_system_startup()
    
    def setup_enterprise_logging(self):
        """Configure comprehensive logging for production monitoring"""
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        # Configure root logger
        self.logger = logging.getLogger('ArbitrageBot')
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # Console Handler (colored for readability)
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console_format = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console.setFormatter(console_format)
        self.logger.addHandler(console)
        
        # File Handler (detailed for debugging)
        file_handler = RotatingFileHandler(
            'logs/bot_system.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=10,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)-20s | %(filename)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        self.logger.addHandler(file_handler)
        
        # Error Handler (separate error log)
        error_handler = TimedRotatingFileHandler(
            'logs/errors.log',
            when='midnight',
            interval=1,
            backupCount=30
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_format)
        self.logger.addHandler(error_handler)
        
        # Performance Metrics Handler
        metrics_handler = RotatingFileHandler(
            'logs/metrics.log',
            maxBytes=5*1024*1024,
            backupCount=5
        )
        metrics_handler.setLevel(logging.INFO)
        metrics_format = logging.Formatter('%(asctime)s | %(message)s')
        metrics_handler.setFormatter(metrics_format)
        
        self.metrics_logger = logging.getLogger('Metrics')
        self.metrics_logger.addHandler(metrics_handler)
        self.metrics_logger.setLevel(logging.INFO)
        
        self.logger.info(f"✅ Enterprise logging initialized for system: {self.system_id}")
    
    def load_configuration(self) -> Dict:
        """Load and validate configuration file"""
        default_config = {
            "system": {
                "max_cycles_per_day": 10000,
                "emergency_stop_loss": -1000.0,
                "daily_profit_target": 500.0,
                "max_drawdown_percent": 5.0
            },
            "exchanges": {
                "enabled": ["kraken", "binance", "coinbase"],
                "timeout_seconds": 30,
                "retry_attempts": 3
            },
            "trading": {
                "max_concurrent_trades": 2,
                "cooldown_after_loss_seconds": 60,
                "position_sizing_mode": "dynamic",  # dynamic, fixed, aggressive
                "risk_per_trade_percent": 1.0
            },
            "monitoring": {
                "health_check_interval": 300,
                "metrics_report_interval": 60,
                "alert_on_api_error_rate": 0.3
            }
        }
        
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    user_config = json.load(f)
                    # Deep merge with defaults
                    self.merge_configs(default_config, user_config)
            
            # Save the merged config for reference
            with open('logs/active_config.json', 'w') as f:
                json.dump(default_config, f, indent=2)
                
            self.logger.info(f"✅ Configuration loaded from {self.config_path}")
            return default_config
            
        except Exception as e:
            self.logger.warning(f"⚠️  Config load failed, using defaults: {e}")
            return default_config
    
    def merge_configs(self, base: Dict, update: Dict):
        """Recursively merge configuration dictionaries"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self.merge_configs(base[key], value)
            else:
                base[key] = value
    
    def initialize_settings(self):
        """Initialize trading settings with validation"""
        settings = {
            'min_trade_amount': 0.000205,
            'min_order_value': 10.0,
            'position_size': 500.0,
            'gold_vault_percentage': 0.1,
            'chaser_attempts': 2,
            'min_btc_per_exchange': 0.001,
            'min_stable_per_exchange': 1500.0,
            'min_bnb_for_binance': 0.1,
            'max_position_size': 5000.0,
            'min_profit_threshold': 0.50,  # Minimum $ profit per trade
            'slippage_tolerance_percent': 0.1,
            'max_trades_per_hour': 20
        }
        
        # Apply any config overrides
        if 'trading' in self.config:
            for key in ['position_size', 'min_profit_threshold', 'slippage_tolerance_percent']:
                if key in self.config['trading']:
                    settings[key] = self.config['trading'][key]
        
        return settings
    
    def initialize_components(self):
        """Initialize all system components with proper error isolation"""
        self.logger.info("🔄 Initializing system components...")
        
        # FIX: Initialize exchange_assets BEFORE it's used in inventory management
        self.exchange_assets = {
            'kraken': {'stablecoins': ['USDT', 'USD', 'USDC'], 'fee_token': None},
            'binance': {'stablecoins': ['USDT', 'BUSD', 'USDC'], 'fee_token': 'BNB'},
            'coinbase': {'stablecoins': ['USDT', 'USD', 'USDC'], 'fee_token': None}
        }
        
        # Phase 1: Exchange Connections (CRITICAL)
        try:
            self.exchanges = self.initialize_exchanges()
            if not self.exchanges:
                raise RuntimeError("No exchanges initialized")
        except Exception as e:
            self.logger.critical(f"❌ Failed to initialize exchanges: {e}")
            sys.exit(1)
        
        # Phase 2: Market Intelligence (IMPORTANT)
        try:
            self.market_context = MarketContext()
            self.auction_analyzer = AuctionContextModule()
            self.logger.info("✅ Market intelligence modules initialized")
        except Exception as e:
            self.logger.error(f"⚠️  Market intelligence initialization failed: {e}")
            # Continue without market intelligence (degraded mode)
            self.market_context = None
            self.auction_analyzer = None
        
        # Phase 3: Monitoring & Health (IMPORTANT)
        try:
            self.health_monitor = HealthMonitor(window_size=50)
            self.rebalance_monitor = RebalanceMonitor()
            self.logger.info("✅ Monitoring systems initialized")
        except Exception as e:
            self.logger.error(f"⚠️  Monitoring initialization failed: {e}")
            # Create minimal health monitor
            self.health_monitor = None
            self.rebalance_monitor = None
        
        # Phase 4: Data Infrastructure (CRITICAL)
        try:
            self.current_latency = self.measure_exchange_latency()
            self.bot_mode = 'HIGH_LATENCY' if self.current_latency > 100 else 'LOW_LATENCY'
            self.initialize_executor()
            self.logger.info(f"✅ Data infrastructure initialized - Mode: {self.bot_mode}")
        except Exception as e:
            self.logger.critical(f"❌ Data infrastructure failed: {e}")
            sys.exit(1)
        
        # Phase 5: Optional Components
        try:
            self.data_hub = DataHub()
            self.use_data_hub = self.config.get('data', {}).get('use_data_hub', False)
            if self.use_data_hub:
                self.logger.info("✅ DataHub initialized (standby mode)")
        except Exception as e:
            self.logger.warning(f"⚠️  DataHub initialization failed: {e}")
            self.data_hub = None
            self.use_data_hub = False
        
        self.logger.info("🎯 All system components initialized successfully")
    
    def initialize_exchanges(self) -> Dict:
        """Initialize exchange connections with comprehensive error handling"""
        exchanges = {}
        exchange_configs = {
            'kraken': {
                'apiKey': os.getenv('KRAKEN_KEY'),
                'secret': os.getenv('KRAKEN_SECRET'),
                'enableRateLimit': True,
                'timeout': 30000,
                'nonce': lambda: int(time.time() * 1000),
                'options': {
                    'adjustForTimeDifference': True,
                    'defaultType': 'spot'
                }
            },
            'binance': {
                'apiKey': os.getenv('BINANCE_KEY'),
                'secret': os.getenv('BINANCE_SECRET'),
                'enableRateLimit': True,
                'timeout': 30000,
                'options': {
                    'defaultType': 'spot',
                    'warnOnFetchOpenOrdersWithoutSymbol': False
                }
            },
            'coinbase': {
                'apiKey': os.getenv('COINBASE_KEY'),
                'secret': os.getenv('COINBASE_SECRET'),
                'enableRateLimit': True,
                'timeout': 30000
            }
        }
        
        enabled_exchanges = self.config['exchanges']['enabled']
        timeout = self.config['exchanges']['timeout_seconds']
        
        for name in enabled_exchanges:
            if name not in exchange_configs:
                self.logger.warning(f"⚠️  Unknown exchange: {name}")
                continue
            
            try:
                config = exchange_configs[name].copy()
                config['timeout'] = timeout * 1000  # Convert to milliseconds
                
                # Exchange-specific initialization
                if name == 'binance':
                    exchange = ccxt.binanceus(config)
                else:
                    exchange_class = getattr(ccxt, name)
                    exchange = exchange_class(config)
                
                # Test connection
                exchange.load_markets()
                
                # Verify we have required markets
                required_pairs = ['BTC/USDT', 'BTC/USDC', 'BTC/USD']
                available_pairs = [pair for pair in required_pairs if pair in exchange.markets]
                
                if not available_pairs:
                    self.logger.warning(f"⚠️  {name} has no required trading pairs")
                    continue
                
                exchanges[name] = exchange
                self.logger.info(f"✅ {name.upper()} connected - Pairs: {len(available_pairs)}/{len(required_pairs)}")
                
            except ccxt.AuthenticationError as e:
                self.logger.error(f"❌ {name} authentication failed: {e}")
            except ccxt.NetworkError as e:
                self.logger.error(f"❌ {name} network error: {e}")
            except ccxt.ExchangeError as e:
                self.logger.error(f"❌ {name} exchange error: {e}")
            except Exception as e:
                self.logger.error(f"❌ {name} initialization error: {e}")
        
        if len(exchanges) < 2:
            self.logger.critical(f"❌ Insufficient exchanges initialized: {len(exchanges)}/2 minimum")
            raise RuntimeError("Insufficient exchange connections")
        
        return exchanges
    
    def measure_exchange_latency(self) -> float:
        """Measure network latency to exchanges with multiple samples"""
        latencies = []
        endpoints = [
            ('Kraken', 'https://api.kraken.com/0/public/Time'),
            ('Binance', 'https://api.binance.com/api/v3/time'),
            ('Coinbase', 'https://api.coinbase.com/v2/time')
        ]
        
        for name, endpoint in endpoints:
            for attempt in range(3):  # 3 attempts per endpoint
                try:
                    start = time.perf_counter()
                    result = subprocess.run(
                        ['curl', '-s', '-m', '5', endpoint],
                        capture_output=True,
                        text=True,
                        timeout=6
                    )
                    
                    if result.returncode == 0:
                        latency = (time.perf_counter() - start) * 1000
                        latencies.append(latency)
                        self.logger.debug(f"  {name} latency: {latency:.1f}ms (attempt {attempt+1})")
                        break  # Success, move to next endpoint
                    else:
                        self.logger.warning(f"  {name} attempt {attempt+1} failed: {result.returncode}")
                        
                except subprocess.TimeoutExpired:
                    self.logger.warning(f"  {name} attempt {attempt+1} timed out")
                except Exception as e:
                    self.logger.debug(f"  {name} attempt {attempt+1} error: {e}")
                
                if attempt < 2:  # Don't sleep after last attempt
                    time.sleep(0.5)
        
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            self.logger.info(f"📡 Network latency: {avg_latency:.1f}ms (samples: {len(latencies)})")
            return avg_latency
        
        self.logger.warning("⚠️  Latency measurement failed, using default: 150ms")
        return 150.0
    
    def initialize_executor(self):
        """Initialize the appropriate order executor based on latency"""
        # Simple fee manager for now
        class SimpleFeeManager:
            def get_current_taker_fee(self, exchange_name, trade_value_usd=0):
                return {"effective_fee_rate": 0.001, "discount_active": False}
        
        self.fee_manager = SimpleFeeManager()
        
        if self.bot_mode == 'HIGH_LATENCY':
            self.order_executor = HighLatencyExecutor(self.fee_manager)
            self.data_feed_class = RESTPollingFeed
            self.logger.info("🔄 HIGH_LATENCY mode activated (REST polling)")
        else:
            self.order_executor = LowLatencyExecutor(self.fee_manager)
            self.data_feed_class = WebSocketFeed
            self.logger.info("⚡ LOW_LATENCY mode activated (WebSocket)")
    
    def register_signal_handlers(self):
        """Register signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.warning(f"🚨 Received signal {signum}, initiating graceful shutdown...")
            self.is_shutting_down = True
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def log_system_startup(self):
        """Log comprehensive system startup information"""
        self.logger.info("=" * 70)
        self.logger.info("🚀 PROFESSIONAL ARBITRAGE TRADING SYSTEM")
        self.logger.info(f"   System ID: {self.system_id}")
        self.logger.info(f"   Version: 2.0.0 | Architecture: Microservices Integration")
        self.logger.info(f"   Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"   PID: {os.getpid()}")
        self.logger.info(f"   Python: {sys.version}")
        self.logger.info(f"   Platform: {platform.platform()}")
        self.logger.info("-" * 70)
        self.logger.info("📊 SYSTEM CONFIGURATION:")
        self.logger.info(f"   Mode: {self.bot_mode}")
        self.logger.info(f"   Latency: {self.current_latency:.1f}ms")
        self.logger.info(f"   Exchanges: {len(self.exchanges)} connected")
        self.logger.info(f"   Min Stable/Exchange: ${self.settings['min_stable_per_exchange']}")
        self.logger.info(f"   Position Size: ${self.settings['position_size']}")
        self.logger.info(f"   Min Profit/Trade: ${self.settings['min_profit_threshold']}")
        self.logger.info("=" * 70)
    
    async def run_async(self):
        """Main trading loop with comprehensive error handling and monitoring"""
        self.logger.info("🏁 Starting main trading loop...")
        
        # Initialize data feed
        try:
            self.data_feed = self.data_feed_class(self.exchanges)
            await self.data_feed.start()
            self.logger.info(f"✅ Data feed started: {self.data_feed_class.__name__}")
        except Exception as e:
            self.logger.critical(f"❌ Failed to start data feed: {e}")
            return
        
        # Main trading loop
        cycle_count = 0
        last_metrics_report = time.time()
        last_health_check = time.time()
        
        try:
            while not self.is_shutting_down:
                cycle_start = time.time()
                cycle_count += 1
                self.system_metrics.cycle_count = cycle_count
                
                try:
                    # ==================== CYCLE START ====================
                    self.logger.debug(f"\n🔄 Cycle #{cycle_count} | Mode: {self.bot_mode}")
                    
                    # Update heartbeat
                    self.last_heartbeat = time.time()
                    
                    # ==================== DATA COLLECTION ====================
                    symbols = [
                        'BTC/USDT', 'BTC/USDC', 'BTC/USD',
                        'BNB/BTC', 'BNB/USDT', 'BNB/USDC',
                        'PAXG/BTC', 'PAXG/USDT', 'PAXG/USD'
                    ]
                    
                    price_data = await self.data_feed.get_prices(symbols)
                    
                    # ==================== MARKET ANALYSIS ====================
                    market_context = await self.analyze_market_context(price_data)
                    
                    # ==================== EXCHANGE STATUS ====================
                    exchange_wrappers = await self.get_exchange_wrappers()
                    
                    # ==================== INVENTORY MANAGEMENT ====================
                    if exchange_wrappers and price_data:
                        await self.manage_inventory(exchange_wrappers, price_data, market_context)
                    
                    # ==================== ARBITRAGE SEARCH ====================
                    opportunities = self.find_arbitrage_opportunities(
                        price_data, 
                        ['BTC/USDT', 'BTC/USDC'],
                        market_context
                    )
                    
                    # ==================== TRADE EXECUTION ====================
                    if opportunities and not self.is_shutting_down:
                        await self.execute_opportunities(opportunities, market_context)
                    
                    # ==================== SYSTEM MAINTENANCE ====================
                    current_time = time.time()
                    
                    # Health check every 5 minutes
                    if current_time - last_health_check > 300:
                        await self.perform_health_check()
                        last_health_check = current_time
                    
                    # Metrics report every minute
                    if current_time - last_metrics_report > 60:
                        self.report_system_metrics()
                        last_metrics_report = current_time
                    
                    # ==================== CYCLE COMPLETION ====================
                    cycle_time = time.time() - cycle_start
                    self.system_metrics.avg_trade_time_ms = (
                        self.system_metrics.avg_trade_time_ms * 0.9 + cycle_time * 1000 * 0.1
                    )
                    
                    # Dynamic sleep based on health monitor
                    if self.health_monitor:
                        sleep_time = self.health_monitor.adjust_cycle_time(cycle_time, self.bot_mode)
                    else:
                        sleep_time = 5.0 if self.bot_mode == 'HIGH_LATENCY' else 1.0
                    
                    await asyncio.sleep(max(0.1, sleep_time))
                    
                except asyncio.CancelledError:
                    self.logger.info("🛑 Trading loop cancelled")
                    break
                except Exception as e:
                    self.logger.error(f"❌ Cycle #{cycle_count} failed: {e}", exc_info=True)
                    await asyncio.sleep(5.0)  # Longer sleep on error
                
        except Exception as e:
            self.logger.critical(f"💥 Main loop crashed: {e}", exc_info=True)
        
        finally:
            # ==================== GRACEFUL SHUTDOWN ====================
            await self.shutdown_system()
    
    async def analyze_market_context(self, price_data) -> Optional[MarketContext]:
        """Analyze market context using auction theory and microstructure"""
        try:
            if not hasattr(self.data_feed, 'market_contexts'):
                return None
            
            # Get primary symbol context
            primary_symbol = 'BTC/USDT'
            if primary_symbol in self.data_feed.market_contexts:
                context = self.data_feed.market_contexts[primary_symbol]
                
                # Log significant context changes
                context_dict = context.to_dict()
                if context.auction_state != AuctionState.BALANCED:
                    self.logger.info(
                        f"🧠 Market: {context_dict['auction']} | "
                        f"Score: {context_dict['auction_score']:.3f} | "
                        f"Confidence: {context_dict['confidence']:.1f} | "
                        f"Crowd: {context_dict['crowd']}"
                    )
                
                return context
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Market context analysis failed: {e}")
            return None
    
    async def get_exchange_wrappers(self):
        """Get exchange wrappers with comprehensive error handling and debug logging"""
        exchange_wrappers = {}
        
        for exch_name, exchange in self.exchanges.items():
            try:
                self.logger.info(f"🔄 Fetching balance for {exch_name.upper()}...")
                
                # 1. FETCH BALANCE
                raw_balance_data = exchange.fetch_balance()
                self.logger.debug(f"📦 Raw balance data type for {exch_name}: {type(raw_balance_data)}")
                
                # 2. SAFE EXTRACTION OF BALANCE DICTIONARIES
                free_balances = {}
                total_balances = {}
                
                # Handle the raw balance data structure
                if isinstance(raw_balance_data, dict):
                    # Log all top-level keys for debugging
                    self.logger.debug(f"   Top-level keys: {list(raw_balance_data.keys())}")
                    
                    # Extract 'free' and 'total' - PRIMARY FIX IS HERE
                    # Some exchanges return these as dicts, others differently
                    free_field = raw_balance_data.get('free')
                    total_field = raw_balance_data.get('total')
                    
                    self.logger.debug(f"   'free' field type: {type(free_field)}")
                    self.logger.debug(f"   'total' field type: {type(total_field)}")
                    
                    # CASE 1: Both are dictionaries (standard CCXT structure)
                    if isinstance(free_field, dict) and isinstance(total_field, dict):
                        free_balances = free_field
                        total_balances = total_field
                    
                    # CASE 2: 'info' contains the actual data (some exchanges)
                    elif 'info' in raw_balance_data and isinstance(raw_balance_data['info'], dict):
                        info_data = raw_balance_data['info']
                        self.logger.debug(f"   Using 'info' field, keys: {list(info_data.keys())[:5]}...")
                        
                        # Try to find balance data in info
                        for key, value in info_data.items():
                            if isinstance(value, (int, float, str)):
                                try:
                                    num_val = float(value)
                                    if num_val > 0:
                                        free_balances[key.upper()] = num_val
                                        total_balances[key.upper()] = num_val
                                except:
                                    pass
                    
                    # CASE 3: Raw data is already the balance dict
                    else:
                        # Check if raw data has currency-like keys
                        currency_keys = [k for k in raw_balance_data.keys() if isinstance(k, str) and len(k) <= 6]
                        if currency_keys:
                            for key in currency_keys:
                                val = raw_balance_data[key]
                                if isinstance(val, (int, float)):
                                    free_balances[key.upper()] = float(val)
                                    total_balances[key.upper()] = float(val)
                
                # 3. CREATE THE WRAPPER CLASS WITH SAFE ACCESS
                class ExchangeWrapper:
                    def __init__(self, name, exchange_obj, free_bal, total_bal):
                        self.name = name
                        self.exchange = exchange_obj
                        self.balances = {}
                        self.free_balances = {}
                        
                        # Track currencies we care about
                        target_currencies = ['BTC', 'USDT', 'USDC', 'USD', 'BNB', 'PAXG']
                        
                        for currency in target_currencies:
                            # Safe extraction from free_balances
                            free_val = 0.0
                            if isinstance(free_bal, dict):
                                # Try exact match
                                if currency in free_bal:
                                    free_val = free_bal[currency]
                                # Try case-insensitive match
                                else:
                                    for k, v in free_bal.items():
                                        if isinstance(k, str) and k.upper() == currency:
                                            free_val = v
                                            break
                            
                            # Safe extraction from total_balances  
                            total_val = 0.0
                            if isinstance(total_bal, dict):
                                if currency in total_bal:
                                    total_val = total_bal[currency]
                                else:
                                    for k, v in total_bal.items():
                                        if isinstance(k, str) and k.upper() == currency:
                                            total_val = v
                                            break
                            
                            # Only store if we have some balance
                            if free_val > 0 or total_val > 0:
                                self.free_balances[currency] = free_val
                                self.balances[currency] = total_val
                        
                        # Calculate total value in USD
                        btc_price_est = 90000  # Conservative estimate
                        self.total_value = (
                            self.balances.get('BTC', 0) * btc_price_est +
                            self.balances.get('USDT', 0) +
                            self.balances.get('USDC', 0) +
                            self.balances.get('USD', 0)
                        )
                
                # 4. CREATE AND STORE THE WRAPPER
                wrapper = ExchangeWrapper(exch_name, exchange, free_balances, total_balances)
                exchange_wrappers[exch_name] = wrapper
                
                # 5. LOG SUCCESS
                btc_display = wrapper.free_balances.get('BTC', 0)
                usdt_display = wrapper.free_balances.get('USDT', 0)
                
                self.logger.info(f"✅ {exch_name.upper()} Balance: "
                               f"BTC={btc_display:.6f}, "
                               f"USDT=${usdt_display:.2f}, "
                               f"Total≈${wrapper.total_value:.2f}")
                
            except ccxt.NetworkError as e:
                self.logger.warning(f"⚠️  Network error fetching {exch_name} balance: {e}")
            except ccxt.ExchangeError as e:
                self.logger.warning(f"⚠️  Exchange error fetching {exch_name} balance: {e}")
            except Exception as e:
                self.logger.error(f"❌ Unexpected error fetching {exch_name} balance: {e}")
                import traceback
                self.logger.error(f"Traceback: {traceback.format_exc()}")
        
        return exchange_wrappers
    
    async def manage_inventory(self, exchange_wrappers, price_data, market_context):
        """Manage inventory with market context awareness"""
        try:
            # Check inventory needs
            inventory_problem = self._check_inventory_needs(exchange_wrappers, price_data)
            
            if inventory_problem:
                self.logger.info(
                    f"⚖️ Inventory: {inventory_problem['exchange'].upper()} "
                    f"low on {inventory_problem['currency']}"
                )
                
                # Format display values
                if inventory_problem['currency'] == 'BTC':
                    current_str = f"{inventory_problem['current']:.6f} BTC"
                    required_str = f"{inventory_problem['required']:.6f} BTC"
                elif inventory_problem['currency'] == 'BNB':
                    current_str = f"{inventory_problem['current']:.3f} BNB"
                    required_str = f"{inventory_problem['required']:.3f} BNB"
                else:
                    current_str = f"${inventory_problem['current']:.2f}"
                    required_str = f"${inventory_problem['required']:.2f}"
                
                self.logger.info(f"   Current: {current_str} | Required: {required_str}")
                
                # Execute rebalancing with market context consideration
                if market_context and market_context.execution_confidence > 0.5:
                    success = await self.order_executor.execute_inventory_rebalance(
                        exchange_wrappers,
                        self.exchanges,
                        price_data,
                        self.settings,
                        inventory_problem,
                        self.exchange_assets
                    )
                    
                    if not success:
                        self.logger.warning("⚠️ Inventory rebalancing failed")
                else:
                    self.logger.info("   ⏸️  Waiting for better market conditions")
                    
        except Exception as e:
            self.logger.error(f"Inventory management error: {e}")
    
    def _check_inventory_needs(self, exchange_wrappers, price_data):
        """Check inventory needs with hysteresis to prevent flapping"""
        problems = []
        
        for name, wrapper in exchange_wrappers.items():
            # FIX: self.exchange_assets is now initialized in initialize_components()
            assets = self.exchange_assets.get(name, {})
            stablecoins = assets.get('stablecoins', [])
            fee_token = assets.get('fee_token')
            min_fee_token = self.settings.get('min_bnb_for_binance', 0.1) if fee_token else 0
            
            # Check BTC with 1% tolerance
            btc_balance = wrapper.free_balances.get('BTC', 0)
            required_btc = self.settings['min_btc_per_exchange']
            if btc_balance < (required_btc * 0.99):
                problems.append({
                    'exchange': name,
                    'currency': 'BTC',
                    'current': btc_balance,
                    'required': required_btc,
                    'deficit': required_btc - btc_balance
                })
            
            # Check stablecoins with 1% tolerance
            stable_balance = 0.0
            for coin in stablecoins:
                stable_balance += wrapper.free_balances.get(coin, 0)
            
            required_stable = self.settings['min_stable_per_exchange']
            if stable_balance < (required_stable * 0.99):
                problems.append({
                    'exchange': name,
                    'currency': 'STABLE',
                    'current': stable_balance,
                    'required': required_stable,
                    'deficit': required_stable - stable_balance,
                    'details': f"Checked: {stablecoins}"
                })
            
            # Check BNB with 5% tolerance (more sensitive)
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
    
    def find_arbitrage_opportunities(self, price_data, symbols, market_context):
        """Find arbitrage opportunities with market context awareness"""
        opportunities = []
        
        # ==================== PARAMETER CALCULATION ====================
        # Base parameters
        if self.bot_mode == 'HIGH_LATENCY':
            base_spread_pct = 0.3  # 0.3%
            base_position = 2000.0
        else:
            base_spread_pct = 0.5  # 0.5%
            base_position = 500.0
        
        # Market context adjustments
        spread_multiplier = 1.0
        position_multiplier = 1.0
        confidence = 0.5
        
        if market_context:
            confidence = market_context.execution_confidence
            
            if market_context.auction_state == AuctionState.ACCEPTING and confidence > 0.7:
                # Accepting market: be more aggressive
                spread_multiplier = 0.7  # Lower threshold
                position_multiplier = 1.3  # Larger position
                self.logger.debug("   🟢 Market: ACCEPTING - Aggressive mode")
                
            elif market_context.auction_state == AuctionState.REJECTING or confidence < 0.4:
                # Rejecting market: be more conservative
                spread_multiplier = 1.5  # Higher threshold
                position_multiplier = 0.7  # Smaller position
                self.logger.debug("   🔴 Market: REJECTING - Conservative mode")
                
            elif market_context.auction_state in [AuctionState.IMBALANCED_BUYING, AuctionState.IMBALANCED_SELLING]:
                # Imbalanced: cautious
                spread_multiplier = 1.2
                position_multiplier = 0.9
                self.logger.debug("   🟡 Market: IMBALANCED - Cautious mode")
        
        # Apply adjustments with limits
        min_spread_pct = max(0.1, base_spread_pct * spread_multiplier)  # Minimum 0.1%
        position_size = min(
            self.settings['max_position_size'],
            max(self.settings['min_order_value'], base_position * position_multiplier)
        )
        
        self.logger.debug(f"   📊 Trading params: Spread={min_spread_pct:.2f}%, Size=${position_size:.0f}, Confidence={confidence:.2f}")
        
        # ==================== OPPORTUNITY SEARCH ====================
        for symbol in symbols:
            if symbol not in price_data or not price_data[symbol]:
                continue
            
            symbol_data = price_data[symbol]
            
            # Get all exchanges with valid prices
            exchanges_with_prices = [
                (name, data) for name, data in symbol_data.items()
                if data.get('ask') and data.get('bid')
            ]
            
            if len(exchanges_with_prices) < 2:
                continue
            
            # Check ALL possible cross-exchange pairs
            for buy_exchange_name, buy_data in exchanges_with_prices:
                for sell_exchange_name, sell_data in exchanges_with_prices:
                    # Must be different exchanges
                    if buy_exchange_name == sell_exchange_name:
                        continue
                    
                    buy_price = buy_data['ask']
                    sell_price = sell_data['bid']
                    
                    # Must have positive spread
                    if sell_price <= buy_price:
                        continue
                    
                    spread = sell_price - buy_price
                    spread_pct = (spread / buy_price) * 100
                    
                    # Check against dynamic threshold
                    if spread_pct > min_spread_pct:
                        amount = position_size / buy_price
                        
                        # Check minimum trade amount
                        if amount >= self.settings['min_trade_amount']:
                            # Calculate estimated profit
                            estimated_profit = spread * amount
                            estimated_fees = amount * buy_price * 0.001 * 2  # Rough fee estimate
                            net_profit = estimated_profit - estimated_fees
                            
                            # Check minimum profit threshold
                            if net_profit >= self.settings['min_profit_threshold']:
                                opportunity = {
                                    'symbol': symbol,
                                    'buy_exchange': buy_exchange_name,
                                    'sell_exchange': sell_exchange_name,
                                    'buy_price': buy_price,
                                    'sell_price': sell_price,
                                    'spread': spread,
                                    'spread_percentage': spread_pct,
                                    'amount': amount,
                                    'estimated_profit': estimated_profit,
                                    'estimated_fees': estimated_fees,
                                    'net_profit': net_profit,
                                    'market_confidence': confidence,
                                    'auction_state': market_context.auction_state.value if market_context else 'UNKNOWN',
                                    'timestamp': time.time()
                                }
                                
                                opportunities.append(opportunity)
                                
                                self.logger.info(
                                    f"🔍 Opportunity: Buy {symbol} on {buy_exchange_name} at ${buy_price:.2f}, "
                                    f"sell on {sell_exchange_name} at ${sell_price:.2f} | "
                                    f"Spread: ${spread:.2f} ({spread_pct:.2f}%) | "
                                    f"Profit: ${net_profit:.2f} net"
                                )
        
        # Sort by confidence-adjusted profit
        if opportunities:
            opportunities.sort(
                key=lambda x: x['net_profit'] * (1 + x['market_confidence']),
                reverse=True
            )
            
            # Limit number of opportunities per cycle
            max_opportunities = self.config['trading'].get('max_concurrent_trades', 2)
            opportunities = opportunities[:max_opportunities]
        
        return opportunities
    
    async def execute_opportunities(self, opportunities, market_context):
        """Execute arbitrage opportunities with comprehensive monitoring"""
        executed_trades = 0
        
        for opportunity in opportunities:
            if self.is_shutting_down:
                break
            
            try:
                self.logger.info(
                    f"⚡ Executing: {opportunity['symbol']} | "
                    f"Buy: {opportunity['buy_exchange']} | "
                    f"Sell: {opportunity['sell_exchange']} | "
                    f"Profit: ${opportunity['net_profit']:.2f}"
                )
                
                # Execute the arbitrage
                success = await self.order_executor.execute_arbitrage(
                    opportunity,
                    self.exchanges
                )
                
                if success:
                    executed_trades += 1
                    self.system_metrics.total_trades += 1
                    self.system_metrics.total_profit += opportunity['net_profit']
                    
                    # Update win rate
                    wins = self.system_metrics.total_trades * self.system_metrics.win_rate
                    self.system_metrics.win_rate = (wins + 1) / self.system_metrics.total_trades
                    
                    self.logger.info(
                        f"✅ Trade executed successfully! "
                        f"Profit: ${opportunity['net_profit']:.2f} | "
                        f"Win Rate: {self.system_metrics.win_rate:.1%}"
                    )
                    
                    # Check if we've hit daily target
                    daily_target = self.config['system']['daily_profit_target']
                    if self.system_metrics.total_profit >= daily_target:
                        self.logger.info(f"🎯 Daily profit target reached: ${daily_target}")
                        # Could implement cooldown or reduced aggression here
                        
                else:
                    self.logger.warning(f"❌ Trade execution failed")
                    self.system_metrics.total_loss += abs(opportunity['net_profit'])
                    
                    # Update win rate
                    wins = self.system_metrics.total_trades * self.system_metrics.win_rate
                    self.system_metrics.win_rate = wins / (self.system_metrics.total_trades + 1)
                
                # Rate limiting between trades
                if executed_trades > 0:
                    await asyncio.sleep(1.0)
                
            except Exception as e:
                self.logger.error(f"❌ Trade execution error: {e}", exc_info=True)
                
                # Log to health monitor
                if self.health_monitor:
                    self.health_monitor.log_api_error('trade_execution')
    
    async def perform_health_check(self):
        """Perform comprehensive system health check"""
        self.logger.info("🏥 Performing system health check...")
        
        # Check exchange connectivity
        for name, exchange in self.exchanges.items():
            try:
                # Simple ping to check connectivity
                exchange.fetch_time()
                self.logger.debug(f"  ✅ {name.upper()}: Connected")
            except Exception as e:
                self.logger.warning(f"  ⚠️  {name.upper()}: Connection issue - {e}")
        
        # Check system resources
        import psutil
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        self.system_metrics.memory_usage_mb = memory_mb
        
        cpu_percent = process.cpu_percent(interval=1)
        
        self.logger.info(
            f"📊 System Resources: "
            f"Memory: {memory_mb:.1f}MB | "
            f"CPU: {cpu_percent:.1f}% | "
            f"Uptime: {self.system_metrics.uptime_seconds/3600:.1f}h"
        )
        
        # Check for emergency conditions
        emergency_stop = self.config['system']['emergency_stop_loss']
        if self.system_metrics.total_loss >= abs(emergency_stop):
            self.logger.critical(f"🚨 EMERGENCY STOP: Loss limit reached (${emergency_stop})")
            self.is_shutting_down = True
    
    def report_system_metrics(self):
        """Report comprehensive system metrics"""
        self.system_metrics.uptime_seconds = time.time() - self.start_time
        
        metrics = self.system_metrics.to_dict()
        
        # Log to metrics file
        self.metrics_logger.info(json.dumps(metrics))
        
        # Log to console (summary)
        self.logger.info(
            f"📈 System Metrics: "
            f"Cycles: {metrics['cycle_count']} | "
            f"Trades: {metrics['total_trades']} | "
            f"Profit: ${metrics['total_profit']} | "
            f"Win Rate: {metrics['win_rate']:.1%} | "
            f"API Success: {metrics['api_success_rate']:.1%}"
        )
    
    async def shutdown_system(self):
        """Perform graceful system shutdown"""
        self.logger.info("🛑 Initiating graceful system shutdown...")
        
        # Stop data feed
        if hasattr(self, 'data_feed'):
            try:
                await self.data_feed.stop()
                self.logger.info("✅ Data feed stopped")
            except Exception as e:
                self.logger.error(f"❌ Error stopping data feed: {e}")
        
        # Close exchange connections
        for name, exchange in self.exchanges.items():
            try:
                # CCXT doesn't have explicit close, but we can clean up
                self.logger.debug(f"  Closed {name} connection")
            except Exception as e:
                self.logger.debug(f"  Error closing {name}: {e}")
        
        # Final metrics report
        self.report_system_metrics()
        
        # Calculate session summary
        session_duration = time.time() - self.start_time
        hourly_rate = (self.system_metrics.total_profit / session_duration) * 3600
        
        self.logger.info("=" * 70)
        self.logger.info("📊 SESSION SUMMARY:")
        self.logger.info(f"   Duration: {session_duration/3600:.2f} hours")
        self.logger.info(f"   Total Cycles: {self.system_metrics.cycle_count}")
        self.logger.info(f"   Total Trades: {self.system_metrics.total_trades}")
        self.logger.info(f"   Total Profit: ${self.system_metrics.total_profit:.2f}")
        self.logger.info(f"   Total Loss: ${self.system_metrics.total_loss:.2f}")
        self.logger.info(f"   Net P&L: ${self.system_metrics.total_profit - self.system_metrics.total_loss:.2f}")
        self.logger.info(f"   Win Rate: {self.system_metrics.win_rate:.1%}")
        self.logger.info(f"   Hourly Rate: ${hourly_rate:.2f}/hour")
        self.logger.info(f"   Avg Trade Time: {self.system_metrics.avg_trade_time_ms:.1f}ms")
        self.logger.info("=" * 70)
        self.logger.info("👋 System shutdown complete. Goodbye!")
    
    def run(self):
        """Main entry point with exception handling"""
        try:
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            self.logger.info("🛑 Shutdown requested by user")
        except Exception as e:
            self.logger.critical(f"💥 Fatal system error: {e}", exc_info=True)
            sys.exit(1)

# ==================== MAIN EXECUTION ====================
if __name__ == "__main__":
    # Create config directory if it doesn't exist
    os.makedirs('config', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    # Initialize and run the bot
    bot = ArbitrageBot()
    bot.run()#!/usr/bin/env python3
"""
PROFESSIONAL ARBITRAGE TRADING SYSTEM - MAIN ORCHESTRATOR
Version: 2.0.0 | Architecture: Microservices Integration
Author: Quant Trading System | Last Updated: 2026-01-10

This is the central nervous system that integrates all sophisticated components:
1. Market Microstructure Analysis
2. Auction Theory Implementation
3. Health & Performance Monitoring
4. Dynamic Parameter Adjustment
5. Multi-Exchange Coordination
6. Graceful Degradation Systems
"""

import asyncio
import ccxt
import time
import os
import sys
import signal
import subprocess
import platform
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from dotenv import load_dotenv
import json

# ==================== CORE TRADING COMPONENTS ====================
from data_feed import RESTPollingFeed, WebSocketFeed
from rebalance_monitor import RebalanceMonitor
from order_executor import LowLatencyExecutor, HighLatencyExecutor

# ==================== MARKET INTELLIGENCE MODULES ====================
from auction_context_module import AuctionContextModule
from market_context import MarketContext, AuctionState, MarketPhase, MacroSignal
from health_monitor import HealthMonitor
from data_hub import DataHub

# ==================== LOGGING CONFIGURATION ====================
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

class LogLevel(Enum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

@dataclass
class SystemMetrics:
    """Comprehensive system performance tracking"""
    cycle_count: int = 0
    total_trades: int = 0
    total_profit: float = 0.0
    total_loss: float = 0.0
    win_rate: float = 0.0
    avg_trade_time_ms: float = 0.0
    api_success_rate: float = 1.0
    uptime_seconds: float = 0.0
    memory_usage_mb: float = 0.0
    last_system_check: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict:
        return {
            'cycle_count': self.cycle_count,
            'total_trades': self.total_trades,
            'total_profit': round(self.total_profit, 2),
            'total_loss': round(self.total_loss, 2),
            'win_rate': round(self.win_rate, 3),
            'avg_trade_time_ms': round(self.avg_trade_time_ms, 2),
            'api_success_rate': round(self.api_success_rate, 3),
            'uptime_hours': round(self.uptime_seconds / 3600, 2),
            'memory_usage_mb': round(self.memory_usage_mb, 1)
        }

class ArbitrageBot:
    """
    PROFESSIONAL TRADING BOT - MAIN CONTROLLER
    
    Features:
    - Multi-exchange arbitrage with market microstructure awareness
    - Dynamic parameter adjustment based on auction theory
    - Comprehensive health monitoring and self-healing
    - Graceful degradation and failover systems
    - Performance metrics and telemetry
    - Configurable trading strategies
    """
    
    def __init__(self, config_path: str = 'config/bot_config.json'):
        """Initialize all system components with proper error handling"""
        self.start_time = time.time()
        self.system_id = f"ARB_{int(time.time())}_{os.getpid()}"
        self.config_path = config_path
        
        # Initialize logging FIRST
        self.setup_enterprise_logging()
        
        # Load configuration
        self.config = self.load_configuration()
        
        # Initialize system state
        self.system_metrics = SystemMetrics()
        self.is_shutting_down = False
        self.last_heartbeat = time.time()
        
        # Register signal handlers for graceful shutdown
        self.register_signal_handlers()
        
        # Load environment variables
        load_dotenv()
        
        # Initialize core settings with validation
        self.settings = self.initialize_settings()
        
        # Initialize all components
        self.initialize_components()
        
        # Log system initialization
        self.log_system_startup()
    
    def setup_enterprise_logging(self):
        """Configure comprehensive logging for production monitoring"""
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        # Configure root logger
        self.logger = logging.getLogger('ArbitrageBot')
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # Console Handler (colored for readability)
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console_format = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console.setFormatter(console_format)
        self.logger.addHandler(console)
        
        # File Handler (detailed for debugging)
        file_handler = RotatingFileHandler(
            'logs/bot_system.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=10,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)-20s | %(filename)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        self.logger.addHandler(file_handler)
        
        # Error Handler (separate error log)
        error_handler = TimedRotatingFileHandler(
            'logs/errors.log',
            when='midnight',
            interval=1,
            backupCount=30
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_format)
        self.logger.addHandler(error_handler)
        
        # Performance Metrics Handler
        metrics_handler = RotatingFileHandler(
            'logs/metrics.log',
            maxBytes=5*1024*1024,
            backupCount=5
        )
        metrics_handler.setLevel(logging.INFO)
        metrics_format = logging.Formatter('%(asctime)s | %(message)s')
        metrics_handler.setFormatter(metrics_format)
        
        self.metrics_logger = logging.getLogger('Metrics')
        self.metrics_logger.addHandler(metrics_handler)
        self.metrics_logger.setLevel(logging.INFO)
        
        self.logger.info(f"✅ Enterprise logging initialized for system: {self.system_id}")
    
    def load_configuration(self) -> Dict:
        """Load and validate configuration file"""
        default_config = {
            "system": {
                "max_cycles_per_day": 10000,
                "emergency_stop_loss": -1000.0,
                "daily_profit_target": 500.0,
                "max_drawdown_percent": 5.0
            },
            "exchanges": {
                "enabled": ["kraken", "binance", "coinbase"],
                "timeout_seconds": 30,
                "retry_attempts": 3
            },
            "trading": {
                "max_concurrent_trades": 2,
                "cooldown_after_loss_seconds": 60,
                "position_sizing_mode": "dynamic",  # dynamic, fixed, aggressive
                "risk_per_trade_percent": 1.0
            },
            "monitoring": {
                "health_check_interval": 300,
                "metrics_report_interval": 60,
                "alert_on_api_error_rate": 0.3
            }
        }
        
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    user_config = json.load(f)
                    # Deep merge with defaults
                    self.merge_configs(default_config, user_config)
            
            # Save the merged config for reference
            with open('logs/active_config.json', 'w') as f:
                json.dump(default_config, f, indent=2)
                
            self.logger.info(f"✅ Configuration loaded from {self.config_path}")
            return default_config
            
        except Exception as e:
            self.logger.warning(f"⚠️  Config load failed, using defaults: {e}")
            return default_config
    
    def merge_configs(self, base: Dict, update: Dict):
        """Recursively merge configuration dictionaries"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self.merge_configs(base[key], value)
            else:
                base[key] = value
    
    def initialize_settings(self):
        """Initialize trading settings with validation"""
        settings = {
            'min_trade_amount': 0.000205,
            'min_order_value': 10.0,
            'position_size': 500.0,
            'gold_vault_percentage': 0.1,
            'chaser_attempts': 2,
            'min_btc_per_exchange': 0.001,
            'min_stable_per_exchange': 1500.0,
            'min_bnb_for_binance': 0.1,
            'max_position_size': 5000.0,
            'min_profit_threshold': 0.50,  # Minimum $ profit per trade
            'slippage_tolerance_percent': 0.1,
            'max_trades_per_hour': 20
        }
        
        # Apply any config overrides
        if 'trading' in self.config:
            for key in ['position_size', 'min_profit_threshold', 'slippage_tolerance_percent']:
                if key in self.config['trading']:
                    settings[key] = self.config['trading'][key]
        
        return settings
    
    def initialize_components(self):
        """Initialize all system components with proper error isolation"""
        self.logger.info("🔄 Initializing system components...")
        
        # FIX: Initialize exchange_assets BEFORE it's used in inventory management
        self.exchange_assets = {
            'kraken': {'stablecoins': ['USDT', 'USD', 'USDC'], 'fee_token': None},
            'binance': {'stablecoins': ['USDT', 'BUSD', 'USDC'], 'fee_token': 'BNB'},
            'coinbase': {'stablecoins': ['USDT', 'USD', 'USDC'], 'fee_token': None}
        }
        
        # Phase 1: Exchange Connections (CRITICAL)
        try:
            self.exchanges = self.initialize_exchanges()
            if not self.exchanges:
                raise RuntimeError("No exchanges initialized")
        except Exception as e:
            self.logger.critical(f"❌ Failed to initialize exchanges: {e}")
            sys.exit(1)
        
        # Phase 2: Market Intelligence (IMPORTANT)
        try:
            self.market_context = MarketContext()
            self.auction_analyzer = AuctionContextModule()
            self.logger.info("✅ Market intelligence modules initialized")
        except Exception as e:
            self.logger.error(f"⚠️  Market intelligence initialization failed: {e}")
            # Continue without market intelligence (degraded mode)
            self.market_context = None
            self.auction_analyzer = None
        
        # Phase 3: Monitoring & Health (IMPORTANT)
        try:
            self.health_monitor = HealthMonitor(window_size=50)
            self.rebalance_monitor = RebalanceMonitor()
            self.logger.info("✅ Monitoring systems initialized")
        except Exception as e:
            self.logger.error(f"⚠️  Monitoring initialization failed: {e}")
            # Create minimal health monitor
            self.health_monitor = None
            self.rebalance_monitor = None
        
        # Phase 4: Data Infrastructure (CRITICAL)
        try:
            self.current_latency = self.measure_exchange_latency()
            self.bot_mode = 'HIGH_LATENCY' if self.current_latency > 100 else 'LOW_LATENCY'
            self.initialize_executor()
            self.logger.info(f"✅ Data infrastructure initialized - Mode: {self.bot_mode}")
        except Exception as e:
            self.logger.critical(f"❌ Data infrastructure failed: {e}")
            sys.exit(1)
        
        # Phase 5: Optional Components
        try:
            self.data_hub = DataHub()
            self.use_data_hub = self.config.get('data', {}).get('use_data_hub', False)
            if self.use_data_hub:
                self.logger.info("✅ DataHub initialized (standby mode)")
        except Exception as e:
            self.logger.warning(f"⚠️  DataHub initialization failed: {e}")
            self.data_hub = None
            self.use_data_hub = False
        
        self.logger.info("🎯 All system components initialized successfully")
    
    def initialize_exchanges(self) -> Dict:
        """Initialize exchange connections with comprehensive error handling"""
        exchanges = {}
        exchange_configs = {
            'kraken': {
                'apiKey': os.getenv('KRAKEN_KEY'),
                'secret': os.getenv('KRAKEN_SECRET'),
                'enableRateLimit': True,
                'timeout': 30000,
                'nonce': lambda: int(time.time() * 1000),
                'options': {
                    'adjustForTimeDifference': True,
                    'defaultType': 'spot'
                }
            },
            'binance': {
                'apiKey': os.getenv('BINANCE_KEY'),
                'secret': os.getenv('BINANCE_SECRET'),
                'enableRateLimit': True,
                'timeout': 30000,
                'options': {
                    'defaultType': 'spot',
                    'warnOnFetchOpenOrdersWithoutSymbol': False
                }
            },
            'coinbase': {
                'apiKey': os.getenv('COINBASE_KEY'),
                'secret': os.getenv('COINBASE_SECRET'),
                'enableRateLimit': True,
                'timeout': 30000
            }
        }
        
        enabled_exchanges = self.config['exchanges']['enabled']
        timeout = self.config['exchanges']['timeout_seconds']
        
        for name in enabled_exchanges:
            if name not in exchange_configs:
                self.logger.warning(f"⚠️  Unknown exchange: {name}")
                continue
            
            try:
                config = exchange_configs[name].copy()
                config['timeout'] = timeout * 1000  # Convert to milliseconds
                
                # Exchange-specific initialization
                if name == 'binance':
                    exchange = ccxt.binanceus(config)
                else:
                    exchange_class = getattr(ccxt, name)
                    exchange = exchange_class(config)
                
                # Test connection
                exchange.load_markets()
                
                # Verify we have required markets
                required_pairs = ['BTC/USDT', 'BTC/USDC', 'BTC/USD']
                available_pairs = [pair for pair in required_pairs if pair in exchange.markets]
                
                if not available_pairs:
                    self.logger.warning(f"⚠️  {name} has no required trading pairs")
                    continue
                
                exchanges[name] = exchange
                self.logger.info(f"✅ {name.upper()} connected - Pairs: {len(available_pairs)}/{len(required_pairs)}")
                
            except ccxt.AuthenticationError as e:
                self.logger.error(f"❌ {name} authentication failed: {e}")
            except ccxt.NetworkError as e:
                self.logger.error(f"❌ {name} network error: {e}")
            except ccxt.ExchangeError as e:
                self.logger.error(f"❌ {name} exchange error: {e}")
            except Exception as e:
                self.logger.error(f"❌ {name} initialization error: {e}")
        
        if len(exchanges) < 2:
            self.logger.critical(f"❌ Insufficient exchanges initialized: {len(exchanges)}/2 minimum")
            raise RuntimeError("Insufficient exchange connections")
        
        return exchanges
    
    def measure_exchange_latency(self) -> float:
        """Measure network latency to exchanges with multiple samples"""
        latencies = []
        endpoints = [
            ('Kraken', 'https://api.kraken.com/0/public/Time'),
            ('Binance', 'https://api.binance.com/api/v3/time'),
            ('Coinbase', 'https://api.coinbase.com/v2/time')
        ]
        
        for name, endpoint in endpoints:
            for attempt in range(3):  # 3 attempts per endpoint
                try:
                    start = time.perf_counter()
                    result = subprocess.run(
                        ['curl', '-s', '-m', '5', endpoint],
                        capture_output=True,
                        text=True,
                        timeout=6
                    )
                    
                    if result.returncode == 0:
                        latency = (time.perf_counter() - start) * 1000
                        latencies.append(latency)
                        self.logger.debug(f"  {name} latency: {latency:.1f}ms (attempt {attempt+1})")
                        break  # Success, move to next endpoint
                    else:
                        self.logger.warning(f"  {name} attempt {attempt+1} failed: {result.returncode}")
                        
                except subprocess.TimeoutExpired:
                    self.logger.warning(f"  {name} attempt {attempt+1} timed out")
                except Exception as e:
                    self.logger.debug(f"  {name} attempt {attempt+1} error: {e}")
                
                if attempt < 2:  # Don't sleep after last attempt
                    time.sleep(0.5)
        
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            self.logger.info(f"📡 Network latency: {avg_latency:.1f}ms (samples: {len(latencies)})")
            return avg_latency
        
        self.logger.warning("⚠️  Latency measurement failed, using default: 150ms")
        return 150.0
    
    def initialize_executor(self):
        """Initialize the appropriate order executor based on latency"""
        # Simple fee manager for now
        class SimpleFeeManager:
            def get_current_taker_fee(self, exchange_name, trade_value_usd=0):
                return {"effective_fee_rate": 0.001, "discount_active": False}
        
        self.fee_manager = SimpleFeeManager()
        
        if self.bot_mode == 'HIGH_LATENCY':
            self.order_executor = HighLatencyExecutor(self.fee_manager)
            self.data_feed_class = RESTPollingFeed
            self.logger.info("🔄 HIGH_LATENCY mode activated (REST polling)")
        else:
            self.order_executor = LowLatencyExecutor(self.fee_manager)
            self.data_feed_class = WebSocketFeed
            self.logger.info("⚡ LOW_LATENCY mode activated (WebSocket)")
    
    def register_signal_handlers(self):
        """Register signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.warning(f"🚨 Received signal {signum}, initiating graceful shutdown...")
            self.is_shutting_down = True
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def log_system_startup(self):
        """Log comprehensive system startup information"""
        self.logger.info("=" * 70)
        self.logger.info("🚀 PROFESSIONAL ARBITRAGE TRADING SYSTEM")
        self.logger.info(f"   System ID: {self.system_id}")
        self.logger.info(f"   Version: 2.0.0 | Architecture: Microservices Integration")
        self.logger.info(f"   Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"   PID: {os.getpid()}")
        self.logger.info(f"   Python: {sys.version}")
        self.logger.info(f"   Platform: {platform.platform()}")
        self.logger.info("-" * 70)
        self.logger.info("📊 SYSTEM CONFIGURATION:")
        self.logger.info(f"   Mode: {self.bot_mode}")
        self.logger.info(f"   Latency: {self.current_latency:.1f}ms")
        self.logger.info(f"   Exchanges: {len(self.exchanges)} connected")
        self.logger.info(f"   Min Stable/Exchange: ${self.settings['min_stable_per_exchange']}")
        self.logger.info(f"   Position Size: ${self.settings['position_size']}")
        self.logger.info(f"   Min Profit/Trade: ${self.settings['min_profit_threshold']}")
        self.logger.info("=" * 70)
    
    async def run_async(self):
        """Main trading loop with comprehensive error handling and monitoring"""
        self.logger.info("🏁 Starting main trading loop...")
        
        # Initialize data feed
        try:
            self.data_feed = self.data_feed_class(self.exchanges)
            await self.data_feed.start()
            self.logger.info(f"✅ Data feed started: {self.data_feed_class.__name__}")
        except Exception as e:
            self.logger.critical(f"❌ Failed to start data feed: {e}")
            return
        
        # Main trading loop
        cycle_count = 0
        last_metrics_report = time.time()
        last_health_check = time.time()
        
        try:
            while not self.is_shutting_down:
                cycle_start = time.time()
                cycle_count += 1
                self.system_metrics.cycle_count = cycle_count
                
                try:
                    # ==================== CYCLE START ====================
                    self.logger.debug(f"\n🔄 Cycle #{cycle_count} | Mode: {self.bot_mode}")
                    
                    # Update heartbeat
                    self.last_heartbeat = time.time()
                    
                    # ==================== DATA COLLECTION ====================
                    symbols = [
                        'BTC/USDT', 'BTC/USDC', 'BTC/USD',
                        'BNB/BTC', 'BNB/USDT', 'BNB/USDC',
                        'PAXG/BTC', 'PAXG/USDT', 'PAXG/USD'
                    ]
                    
                    price_data = await self.data_feed.get_prices(symbols)
                    
                    # ==================== MARKET ANALYSIS ====================
                    market_context = await self.analyze_market_context(price_data)
                    
                    # ==================== EXCHANGE STATUS ====================
                    exchange_wrappers = await self.get_exchange_wrappers()
                    
                    # ==================== INVENTORY MANAGEMENT ====================
                    if exchange_wrappers and price_data:
                        await self.manage_inventory(exchange_wrappers, price_data, market_context)
                    
                    # ==================== ARBITRAGE SEARCH ====================
                    opportunities = self.find_arbitrage_opportunities(
                        price_data, 
                        ['BTC/USDT', 'BTC/USDC'],
                        market_context
                    )
                    
                    # ==================== TRADE EXECUTION ====================
                    if opportunities and not self.is_shutting_down:
                        await self.execute_opportunities(opportunities, market_context)
                    
                    # ==================== SYSTEM MAINTENANCE ====================
                    current_time = time.time()
                    
                    # Health check every 5 minutes
                    if current_time - last_health_check > 300:
                        await self.perform_health_check()
                        last_health_check = current_time
                    
                    # Metrics report every minute
                    if current_time - last_metrics_report > 60:
                        self.report_system_metrics()
                        last_metrics_report = current_time
                    
                    # ==================== CYCLE COMPLETION ====================
                    cycle_time = time.time() - cycle_start
                    self.system_metrics.avg_trade_time_ms = (
                        self.system_metrics.avg_trade_time_ms * 0.9 + cycle_time * 1000 * 0.1
                    )
                    
                    # Dynamic sleep based on health monitor
                    if self.health_monitor:
                        sleep_time = self.health_monitor.adjust_cycle_time(cycle_time, self.bot_mode)
                    else:
                        sleep_time = 5.0 if self.bot_mode == 'HIGH_LATENCY' else 1.0
                    
                    await asyncio.sleep(max(0.1, sleep_time))
                    
                except asyncio.CancelledError:
                    self.logger.info("🛑 Trading loop cancelled")
                    break
                except Exception as e:
                    self.logger.error(f"❌ Cycle #{cycle_count} failed: {e}", exc_info=True)
                    await asyncio.sleep(5.0)  # Longer sleep on error
                
        except Exception as e:
            self.logger.critical(f"💥 Main loop crashed: {e}", exc_info=True)
        
        finally:
            # ==================== GRACEFUL SHUTDOWN ====================
            await self.shutdown_system()
    
    async def analyze_market_context(self, price_data) -> Optional[MarketContext]:
        """Analyze market context using auction theory and microstructure"""
        try:
            if not hasattr(self.data_feed, 'market_contexts'):
                return None
            
            # Get primary symbol context
            primary_symbol = 'BTC/USDT'
            if primary_symbol in self.data_feed.market_contexts:
                context = self.data_feed.market_contexts[primary_symbol]
                
                # Log significant context changes
                context_dict = context.to_dict()
                if context.auction_state != AuctionState.BALANCED:
                    self.logger.info(
                        f"🧠 Market: {context_dict['auction']} | "
                        f"Score: {context_dict['auction_score']:.3f} | "
                        f"Confidence: {context_dict['confidence']:.1f} | "
                        f"Crowd: {context_dict['crowd']}"
                    )
                
                return context
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Market context analysis failed: {e}")
            return None
    
    async def get_exchange_wrappers(self):
        """Get exchange wrappers with comprehensive error handling and debug logging"""
        exchange_wrappers = {}
        
        for exch_name, exchange in self.exchanges.items():
            try:
                self.logger.info(f"🔄 Fetching balance for {exch_name.upper()}...")
                
                # 1. FETCH BALANCE
                raw_balance_data = exchange.fetch_balance()
                self.logger.debug(f"📦 Raw balance data type for {exch_name}: {type(raw_balance_data)}")
                
                # 2. SAFE EXTRACTION OF BALANCE DICTIONARIES
                free_balances = {}
                total_balances = {}
                
                # Handle the raw balance data structure
                if isinstance(raw_balance_data, dict):
                    # Log all top-level keys for debugging
                    self.logger.debug(f"   Top-level keys: {list(raw_balance_data.keys())}")
                    
                    # Extract 'free' and 'total' - PRIMARY FIX IS HERE
                    # Some exchanges return these as dicts, others differently
                    free_field = raw_balance_data.get('free')
                    total_field = raw_balance_data.get('total')
                    
                    self.logger.debug(f"   'free' field type: {type(free_field)}")
                    self.logger.debug(f"   'total' field type: {type(total_field)}")
                    
                    # CASE 1: Both are dictionaries (standard CCXT structure)
                    if isinstance(free_field, dict) and isinstance(total_field, dict):
                        free_balances = free_field
                        total_balances = total_field
                    
                    # CASE 2: 'info' contains the actual data (some exchanges)
                    elif 'info' in raw_balance_data and isinstance(raw_balance_data['info'], dict):
                        info_data = raw_balance_data['info']
                        self.logger.debug(f"   Using 'info' field, keys: {list(info_data.keys())[:5]}...")
                        
                        # Try to find balance data in info
                        for key, value in info_data.items():
                            if isinstance(value, (int, float, str)):
                                try:
                                    num_val = float(value)
                                    if num_val > 0:
                                        free_balances[key.upper()] = num_val
                                        total_balances[key.upper()] = num_val
                                except:
                                    pass
                    
                    # CASE 3: Raw data is already the balance dict
                    else:
                        # Check if raw data has currency-like keys
                        currency_keys = [k for k in raw_balance_data.keys() if isinstance(k, str) and len(k) <= 6]
                        if currency_keys:
                            for key in currency_keys:
                                val = raw_balance_data[key]
                                if isinstance(val, (int, float)):
                                    free_balances[key.upper()] = float(val)
                                    total_balances[key.upper()] = float(val)
                
                # 3. CREATE THE WRAPPER CLASS WITH SAFE ACCESS
                class ExchangeWrapper:
                    def __init__(self, name, exchange_obj, free_bal, total_bal):
                        self.name = name
                        self.exchange = exchange_obj
                        self.balances = {}
                        self.free_balances = {}
                        
                        # Track currencies we care about
                        target_currencies = ['BTC', 'USDT', 'USDC', 'USD', 'BNB', 'PAXG']
                        
                        for currency in target_currencies:
                            # Safe extraction from free_balances
                            free_val = 0.0
                            if isinstance(free_bal, dict):
                                # Try exact match
                                if currency in free_bal:
                                    free_val = free_bal[currency]
                                # Try case-insensitive match
                                else:
                                    for k, v in free_bal.items():
                                        if isinstance(k, str) and k.upper() == currency:
                                            free_val = v
                                            break
                            
                            # Safe extraction from total_balances  
                            total_val = 0.0
                            if isinstance(total_bal, dict):
                                if currency in total_bal:
                                    total_val = total_bal[currency]
                                else:
                                    for k, v in total_bal.items():
                                        if isinstance(k, str) and k.upper() == currency:
                                            total_val = v
                                            break
                            
                            # Only store if we have some balance
                            if free_val > 0 or total_val > 0:
                                self.free_balances[currency] = free_val
                                self.balances[currency] = total_val
                        
                        # Calculate total value in USD
                        btc_price_est = 90000  # Conservative estimate
                        self.total_value = (
                            self.balances.get('BTC', 0) * btc_price_est +
                            self.balances.get('USDT', 0) +
                            self.balances.get('USDC', 0) +
                            self.balances.get('USD', 0)
                        )
                
                # 4. CREATE AND STORE THE WRAPPER
                wrapper = ExchangeWrapper(exch_name, exchange, free_balances, total_balances)
                exchange_wrappers[exch_name] = wrapper
                
                # 5. LOG SUCCESS
                btc_display = wrapper.free_balances.get('BTC', 0)
                usdt_display = wrapper.free_balances.get('USDT', 0)
                
                self.logger.info(f"✅ {exch_name.upper()} Balance: "
                               f"BTC={btc_display:.6f}, "
                               f"USDT=${usdt_display:.2f}, "
                               f"Total≈${wrapper.total_value:.2f}")
                
            except ccxt.NetworkError as e:
                self.logger.warning(f"⚠️  Network error fetching {exch_name} balance: {e}")
            except ccxt.ExchangeError as e:
                self.logger.warning(f"⚠️  Exchange error fetching {exch_name} balance: {e}")
            except Exception as e:
                self.logger.error(f"❌ Unexpected error fetching {exch_name} balance: {e}")
                import traceback
                self.logger.error(f"Traceback: {traceback.format_exc()}")
        
        return exchange_wrappers
    
    async def manage_inventory(self, exchange_wrappers, price_data, market_context):
        """Manage inventory with market context awareness"""
        try:
            # Check inventory needs
            inventory_problem = self._check_inventory_needs(exchange_wrappers, price_data)
            
            if inventory_problem:
                self.logger.info(
                    f"⚖️ Inventory: {inventory_problem['exchange'].upper()} "
                    f"low on {inventory_problem['currency']}"
                )
                
                # Format display values
                if inventory_problem['currency'] == 'BTC':
                    current_str = f"{inventory_problem['current']:.6f} BTC"
                    required_str = f"{inventory_problem['required']:.6f} BTC"
                elif inventory_problem['currency'] == 'BNB':
                    current_str = f"{inventory_problem['current']:.3f} BNB"
                    required_str = f"{inventory_problem['required']:.3f} BNB"
                else:
                    current_str = f"${inventory_problem['current']:.2f}"
                    required_str = f"${inventory_problem['required']:.2f}"
                
                self.logger.info(f"   Current: {current_str} | Required: {required_str}")
                
                # Execute rebalancing with market context consideration
                if market_context and market_context.execution_confidence > 0.5:
                    success = await self.order_executor.execute_inventory_rebalance(
                        exchange_wrappers,
                        self.exchanges,
                        price_data,
                        self.settings,
                        inventory_problem,
                        self.exchange_assets
                    )
                    
                    if not success:
                        self.logger.warning("⚠️ Inventory rebalancing failed")
                else:
                    self.logger.info("   ⏸️  Waiting for better market conditions")
                    
        except Exception as e:
            self.logger.error(f"Inventory management error: {e}")
    
    def _check_inventory_needs(self, exchange_wrappers, price_data):
        """Check inventory needs with hysteresis to prevent flapping"""
        problems = []
        
        for name, wrapper in exchange_wrappers.items():
            # FIX: self.exchange_assets is now initialized in initialize_components()
            assets = self.exchange_assets.get(name, {})
            stablecoins = assets.get('stablecoins', [])
            fee_token = assets.get('fee_token')
            min_fee_token = self.settings.get('min_bnb_for_binance', 0.1) if fee_token else 0
            
            # Check BTC with 1% tolerance
            btc_balance = wrapper.free_balances.get('BTC', 0)
            required_btc = self.settings['min_btc_per_exchange']
            if btc_balance < (required_btc * 0.99):
                problems.append({
                    'exchange': name,
                    'currency': 'BTC',
                    'current': btc_balance,
                    'required': required_btc,
                    'deficit': required_btc - btc_balance
                })
            
            # Check stablecoins with 1% tolerance
            stable_balance = 0.0
            for coin in stablecoins:
                stable_balance += wrapper.free_balances.get(coin, 0)
            
            required_stable = self.settings['min_stable_per_exchange']
            if stable_balance < (required_stable * 0.99):
                problems.append({
                    'exchange': name,
                    'currency': 'STABLE',
                    'current': stable_balance,
                    'required': required_stable,
                    'deficit': required_stable - stable_balance,
                    'details': f"Checked: {stablecoins}"
                })
            
            # Check BNB with 5% tolerance (more sensitive)
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
    
    def find_arbitrage_opportunities(self, price_data, symbols, market_context):
        """Find arbitrage opportunities with market context awareness"""
        opportunities = []
        
        # ==================== PARAMETER CALCULATION ====================
        # Base parameters
        if self.bot_mode == 'HIGH_LATENCY':
            base_spread_pct = 0.3  # 0.3%
            base_position = 2000.0
        else:
            base_spread_pct = 0.5  # 0.5%
            base_position = 500.0
        
        # Market context adjustments
        spread_multiplier = 1.0
        position_multiplier = 1.0
        confidence = 0.5
        
        if market_context:
            confidence = market_context.execution_confidence
            
            if market_context.auction_state == AuctionState.ACCEPTING and confidence > 0.7:
                # Accepting market: be more aggressive
                spread_multiplier = 0.7  # Lower threshold
                position_multiplier = 1.3  # Larger position
                self.logger.debug("   🟢 Market: ACCEPTING - Aggressive mode")
                
            elif market_context.auction_state == AuctionState.REJECTING or confidence < 0.4:
                # Rejecting market: be more conservative
                spread_multiplier = 1.5  # Higher threshold
                position_multiplier = 0.7  # Smaller position
                self.logger.debug("   🔴 Market: REJECTING - Conservative mode")
                
            elif market_context.auction_state in [AuctionState.IMBALANCED_BUYING, AuctionState.IMBALANCED_SELLING]:
                # Imbalanced: cautious
                spread_multiplier = 1.2
                position_multiplier = 0.9
                self.logger.debug("   🟡 Market: IMBALANCED - Cautious mode")
        
        # Apply adjustments with limits
        min_spread_pct = max(0.1, base_spread_pct * spread_multiplier)  # Minimum 0.1%
        position_size = min(
            self.settings['max_position_size'],
            max(self.settings['min_order_value'], base_position * position_multiplier)
        )
        
        self.logger.debug(f"   📊 Trading params: Spread={min_spread_pct:.2f}%, Size=${position_size:.0f}, Confidence={confidence:.2f}")
        
        # ==================== OPPORTUNITY SEARCH ====================
        for symbol in symbols:
            if symbol not in price_data or not price_data[symbol]:
                continue
            
            symbol_data = price_data[symbol]
            
            # Get all exchanges with valid prices
            exchanges_with_prices = [
                (name, data) for name, data in symbol_data.items()
                if data.get('ask') and data.get('bid')
            ]
            
            if len(exchanges_with_prices) < 2:
                continue
            
            # Check ALL possible cross-exchange pairs
            for buy_exchange_name, buy_data in exchanges_with_prices:
                for sell_exchange_name, sell_data in exchanges_with_prices:
                    # Must be different exchanges
                    if buy_exchange_name == sell_exchange_name:
                        continue
                    
                    buy_price = buy_data['ask']
                    sell_price = sell_data['bid']
                    
                    # Must have positive spread
                    if sell_price <= buy_price:
                        continue
                    
                    spread = sell_price - buy_price
                    spread_pct = (spread / buy_price) * 100
                    
                    # Check against dynamic threshold
                    if spread_pct > min_spread_pct:
                        amount = position_size / buy_price
                        
                        # Check minimum trade amount
                        if amount >= self.settings['min_trade_amount']:
                            # Calculate estimated profit
                            estimated_profit = spread * amount
                            estimated_fees = amount * buy_price * 0.001 * 2  # Rough fee estimate
                            net_profit = estimated_profit - estimated_fees
                            
                            # Check minimum profit threshold
                            if net_profit >= self.settings['min_profit_threshold']:
                                opportunity = {
                                    'symbol': symbol,
                                    'buy_exchange': buy_exchange_name,
                                    'sell_exchange': sell_exchange_name,
                                    'buy_price': buy_price,
                                    'sell_price': sell_price,
                                    'spread': spread,
                                    'spread_percentage': spread_pct,
                                    'amount': amount,
                                    'estimated_profit': estimated_profit,
                                    'estimated_fees': estimated_fees,
                                    'net_profit': net_profit,
                                    'market_confidence': confidence,
                                    'auction_state': market_context.auction_state.value if market_context else 'UNKNOWN',
                                    'timestamp': time.time()
                                }
                                
                                opportunities.append(opportunity)
                                
                                self.logger.info(
                                    f"🔍 Opportunity: Buy {symbol} on {buy_exchange_name} at ${buy_price:.2f}, "
                                    f"sell on {sell_exchange_name} at ${sell_price:.2f} | "
                                    f"Spread: ${spread:.2f} ({spread_pct:.2f}%) | "
                                    f"Profit: ${net_profit:.2f} net"
                                )
        
        # Sort by confidence-adjusted profit
        if opportunities:
            opportunities.sort(
                key=lambda x: x['net_profit'] * (1 + x['market_confidence']),
                reverse=True
            )
            
            # Limit number of opportunities per cycle
            max_opportunities = self.config['trading'].get('max_concurrent_trades', 2)
            opportunities = opportunities[:max_opportunities]
        
        return opportunities
    
    async def execute_opportunities(self, opportunities, market_context):
        """Execute arbitrage opportunities with comprehensive monitoring"""
        executed_trades = 0
        
        for opportunity in opportunities:
            if self.is_shutting_down:
                break
            
            try:
                self.logger.info(
                    f"⚡ Executing: {opportunity['symbol']} | "
                    f"Buy: {opportunity['buy_exchange']} | "
                    f"Sell: {opportunity['sell_exchange']} | "
                    f"Profit: ${opportunity['net_profit']:.2f}"
                )
                
                # Execute the arbitrage
                success = await self.order_executor.execute_arbitrage(
                    opportunity,
                    self.exchanges
                )
                
                if success:
                    executed_trades += 1
                    self.system_metrics.total_trades += 1
                    self.system_metrics.total_profit += opportunity['net_profit']
                    
                    # Update win rate
                    wins = self.system_metrics.total_trades * self.system_metrics.win_rate
                    self.system_metrics.win_rate = (wins + 1) / self.system_metrics.total_trades
                    
                    self.logger.info(
                        f"✅ Trade executed successfully! "
                        f"Profit: ${opportunity['net_profit']:.2f} | "
                        f"Win Rate: {self.system_metrics.win_rate:.1%}"
                    )
                    
                    # Check if we've hit daily target
                    daily_target = self.config['system']['daily_profit_target']
                    if self.system_metrics.total_profit >= daily_target:
                        self.logger.info(f"🎯 Daily profit target reached: ${daily_target}")
                        # Could implement cooldown or reduced aggression here
                        
                else:
                    self.logger.warning(f"❌ Trade execution failed")
                    self.system_metrics.total_loss += abs(opportunity['net_profit'])
                    
                    # Update win rate
                    wins = self.system_metrics.total_trades * self.system_metrics.win_rate
                    self.system_metrics.win_rate = wins / (self.system_metrics.total_trades + 1)
                
                # Rate limiting between trades
                if executed_trades > 0:
                    await asyncio.sleep(1.0)
                
            except Exception as e:
                self.logger.error(f"❌ Trade execution error: {e}", exc_info=True)
                
                # Log to health monitor
                if self.health_monitor:
                    self.health_monitor.log_api_error('trade_execution')
    
    async def perform_health_check(self):
        """Perform comprehensive system health check"""
        self.logger.info("🏥 Performing system health check...")
        
        # Check exchange connectivity
        for name, exchange in self.exchanges.items():
            try:
                # Simple ping to check connectivity
                exchange.fetch_time()
                self.logger.debug(f"  ✅ {name.upper()}: Connected")
            except Exception as e:
                self.logger.warning(f"  ⚠️  {name.upper()}: Connection issue - {e}")
        
        # Check system resources
        import psutil
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        self.system_metrics.memory_usage_mb = memory_mb
        
        cpu_percent = process.cpu_percent(interval=1)
        
        self.logger.info(
            f"📊 System Resources: "
            f"Memory: {memory_mb:.1f}MB | "
            f"CPU: {cpu_percent:.1f}% | "
            f"Uptime: {self.system_metrics.uptime_seconds/3600:.1f}h"
        )
        
        # Check for emergency conditions
        emergency_stop = self.config['system']['emergency_stop_loss']
        if self.system_metrics.total_loss >= abs(emergency_stop):
            self.logger.critical(f"🚨 EMERGENCY STOP: Loss limit reached (${emergency_stop})")
            self.is_shutting_down = True
    
    def report_system_metrics(self):
        """Report comprehensive system metrics"""
        self.system_metrics.uptime_seconds = time.time() - self.start_time
        
        metrics = self.system_metrics.to_dict()
        
        # Log to metrics file
        self.metrics_logger.info(json.dumps(metrics))
        
        # Log to console (summary)
        self.logger.info(
            f"📈 System Metrics: "
            f"Cycles: {metrics['cycle_count']} | "
            f"Trades: {metrics['total_trades']} | "
            f"Profit: ${metrics['total_profit']} | "
            f"Win Rate: {metrics['win_rate']:.1%} | "
            f"API Success: {metrics['api_success_rate']:.1%}"
        )
    
    async def shutdown_system(self):
        """Perform graceful system shutdown"""
        self.logger.info("🛑 Initiating graceful system shutdown...")
        
        # Stop data feed
        if hasattr(self, 'data_feed'):
            try:
                await self.data_feed.stop()
                self.logger.info("✅ Data feed stopped")
            except Exception as e:
                self.logger.error(f"❌ Error stopping data feed: {e}")
        
        # Close exchange connections
        for name, exchange in self.exchanges.items():
            try:
                # CCXT doesn't have explicit close, but we can clean up
                self.logger.debug(f"  Closed {name} connection")
            except Exception as e:
                self.logger.debug(f"  Error closing {name}: {e}")
        
        # Final metrics report
        self.report_system_metrics()
        
        # Calculate session summary
        session_duration = time.time() - self.start_time
        hourly_rate = (self.system_metrics.total_profit / session_duration) * 3600
        
        self.logger.info("=" * 70)
        self.logger.info("📊 SESSION SUMMARY:")
        self.logger.info(f"   Duration: {session_duration/3600:.2f} hours")
        self.logger.info(f"   Total Cycles: {self.system_metrics.cycle_count}")
        self.logger.info(f"   Total Trades: {self.system_metrics.total_trades}")
        self.logger.info(f"   Total Profit: ${self.system_metrics.total_profit:.2f}")
        self.logger.info(f"   Total Loss: ${self.system_metrics.total_loss:.2f}")
        self.logger.info(f"   Net P&L: ${self.system_metrics.total_profit - self.system_metrics.total_loss:.2f}")
        self.logger.info(f"   Win Rate: {self.system_metrics.win_rate:.1%}")
        self.logger.info(f"   Hourly Rate: ${hourly_rate:.2f}/hour")
        self.logger.info(f"   Avg Trade Time: {self.system_metrics.avg_trade_time_ms:.1f}ms")
        self.logger.info("=" * 70)
        self.logger.info("👋 System shutdown complete. Goodbye!")
    
    def run(self):
        """Main entry point with exception handling"""
        try:
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            self.logger.info("🛑 Shutdown requested by user")
        except Exception as e:
            self.logger.critical(f"💥 Fatal system error: {e}", exc_info=True)
            sys.exit(1)

# ==================== MAIN EXECUTION ====================
if __name__ == "__main__":
    # Create config directory if it doesn't exist
    os.makedirs('config', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    # Initialize and run the bot
    bot = ArbitrageBot()
    bot.run()