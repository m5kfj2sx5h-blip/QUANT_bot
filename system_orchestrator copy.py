import asyncio
import ccxt
import time
import os
import subprocess
import platform
from dotenv import load_dotenv
from data_feed import RESTPollingFeed, WebSocketFeed
from rebalance_monitor import RebalanceMonitor
from order_executor import LowLatencyExecutor, HighLatencyExecutor
import logging
from logging.handlers import RotatingFileHandler

class ArbitrageBot:
    def __init__(self):
        self.setup_logging()
        load_dotenv()
        self.settings = {
            'min_trade_amount': 0.000205, 
            'min_order_value': 10.0,
            'position_size': 500.0, 
            'gold_vault_percentage': 0.1, 
            'chaser_attempts': 2
        }
        
        class SimpleFeeManager:
            def get_current_taker_fee(self, exchange_name, trade_value_usd=0):
                return {"effective_fee_rate": 0.001, "discount_active": False}
        
        self.fee_manager = SimpleFeeManager()
        self.exchanges = self.initialize_exchanges()
        self.mode_switch_counter = 0
        self.mode_check_interval = 30
        
        # Initial mode detection
        self.current_latency = self.measure_exchange_latency()
        self.bot_mode = 'HIGH_LATENCY' if self.current_latency > 100 else 'LOW_LATENCY'
        
        # Initialize components based on mode
        self.initialize_components()
        
        logging.info("🎯 Arbitrage Bot Initialized")
        logging.info(f"🚀 Starting SMART Dual-Mode Arbitrage Bot | Latency: {self.current_latency:.2f} ms | Mode: {self.bot_mode}")
        
    def setup_logging(self):
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        fh = RotatingFileHandler('bot_log.log', maxBytes=10485760, backupCount=5)
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        fh.setFormatter(formatter)
        logger.addHandler(ch)
        logger.addHandler(fh)
        
    def measure_exchange_latency(self):
        """Measure actual latency to exchange APIs"""
        latencies = []
        endpoints = [
            'https://api.kraken.com/0/public/Time',
            'https://api.binance.com/api/v3/time',
            'https://api.coinbase.com/v2/time'
        ]
        
        for endpoint in endpoints:
            try:
                start = time.time()
                result = subprocess.run(
                    ['curl', '-s', endpoint],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    latency = (time.time() - start) * 1000
                    latencies.append(latency)
            except:
                continue
        
        if latencies:
            return sum(latencies) / len(latencies)
        return 150.0
    
    def initialize_exchanges(self):
        """Initialize all exchanges with proper authentication"""
        logging.info("Initializing exchanges...")
        exchanges = {}
        exchange_configs = {
            'kraken': {
                'apiKey': os.getenv('KRAKEN_KEY'),
                'secret': os.getenv('KRAKEN_SECRET'),
                'enableRateLimit': True,
                'nonce': lambda: int(time.time() * 1000),
                'options': {'adjustForTimeDifference': True}
            },
            'binance': {
                'apiKey': os.getenv('BINANCE_KEY'),
                'secret': os.getenv('BINANCE_SECRET'),
                'enableRateLimit': True
            },
            'coinbase': {
                'apiKey': os.getenv('COINBASE_KEY'),
                'secret': os.getenv('COINBASE_SECRET'),
                'enableRateLimit': True
            }
        }
        
        for name, config in exchange_configs.items():
            try:
                if name == 'binance':
                    exchange = ccxt.binanceus(config)
                else:
                    exchange = getattr(ccxt, name)(config)
                
                exchange.load_markets()
                exchanges[name] = exchange
                logging.info(f"✅ {name.upper()} connected")
                
            except Exception as e:
                logging.error(f"❌ Failed to initialize {name}: {e}")
        
        return exchanges
    
    def initialize_components(self):
        """Initialize or reinitialize components based on current mode"""
        if self.bot_mode == 'HIGH_LATENCY':
            self.order_executor = HighLatencyExecutor(self.fee_manager)
            logging.info("🔄 Switched to HIGH_LATENCY executor")
        else:
            self.order_executor = LowLatencyExecutor(self.fee_manager)
            logging.info("🔄 Switched to LOW_LATENCY executor")
        
        self.rebalance_monitor = RebalanceMonitor()
    
    def check_and_update_mode(self):
        """Check if mode needs to be updated based on current latency"""
        self.mode_switch_counter += 1
        
        if self.mode_switch_counter >= self.mode_check_interval:
            self.mode_switch_counter = 0
            new_latency = self.measure_exchange_latency()
            
            new_mode = 'HIGH_LATENCY' if new_latency > 100 else 'LOW_LATENCY'
            
            if new_mode != self.bot_mode:
                self.bot_mode = new_mode
                self.current_latency = new_latency
                self.initialize_components()
                logging.info(f"🔄 Mode switched to {self.bot_mode} based on latency: {new_latency:.2f} ms")
                return True
        
        return False
    
    async def run_async(self):
        """Main async loop"""
        logging.info("🏁 Starting main arbitrage loop...")
        
        # Initialize data feed based on current mode
        if self.bot_mode == 'HIGH_LATENCY':
            self.data_feed = RESTPollingFeed(self.exchanges)
        else:
            self.data_feed = WebSocketFeed(self.exchanges)
        
        await self.data_feed.start()
        cycle_count = 0
        
        try:
            while True:
                cycle_count += 1
                logging.info(f"\n🔄 Cycle #{cycle_count} | Mode: {self.bot_mode}")
                
                # Check and update mode if needed
                self.check_and_update_mode()
                
                # Step 1: Get current balances
                exchange_wrappers = await self.get_exchange_wrappers()
                
                # Step 2: Get price data
                symbols = ['BTC/USDT', 'BTC/USDC']
                price_data = await self.data_feed.get_prices(symbols)
                
                # Step 3: Log BTC price if available
                btc_price = None
                for symbol in symbols:
                    if symbol in price_data and price_data[symbol]:
                        for exch_data in price_data[symbol].values():
                            if exch_data.get('bid'):
                                btc_price = exch_data['bid']
                                logging.info(f"📈 BTC Price: ${btc_price:.2f}")
                                break
                        if btc_price:
                            break
                
                # Step 4: Rebalance if needed (BUY BTC with stablecoins)
                if exchange_wrappers and price_data:
                    try:
                        needs_rebalance = self.rebalance_monitor.should_rebalance(exchange_wrappers, price_data)
                        if needs_rebalance:
                            logging.info("⚖️ Rebalance needed - Buying BTC with stablecoins")
                            
                            # Get available stablecoins
                            available_stable = self.calculate_available_stablecoins(exchange_wrappers)
                            
                            if available_stable > self.settings['min_order_value']:
                                # Execute rebalancing to buy BTC
                                success = await self.order_executor.execute_rebalancing(
                                    exchange_wrappers, 
                                    self.exchanges, 
                                    price_data,
                                    self.settings
                                )
                                
                                if not success:
                                    logging.warning("⚠️ Rebalancing failed, continuing with available funds")
                            else:
                                logging.info("💰 Insufficient stablecoins for rebalancing")
                    
                    except Exception as e:
                        logging.error(f"Rebalance check error: {e}")
                
                # Step 5: Look for arbitrage opportunities
                opportunities = self.find_arbitrage_opportunities(price_data, symbols)
                
                # Step 6: Execute best arbitrage opportunity
                if opportunities:
                    best_opportunity = max(opportunities, key=lambda x: x['spread_percentage'])
                    
                    try:
                        success = await self.order_executor.execute_arbitrage(
                            best_opportunity, 
                            self.exchanges
                        )
                        
                        if success:
                            profit = (best_opportunity['sell_price'] - best_opportunity['buy_price']) * best_opportunity['amount']
                            vault_cut = profit * self.settings['gold_vault_percentage']
                            logging.info(f"✅ Arbitrage executed. Profit: ${profit:.2f}, Vault: ${vault_cut:.2f}")
                    
                    except Exception as e:
                        logging.error(f"❌ Arbitrage execution failed: {e}")
                else:
                    logging.info("🔍 No arbitrage opportunities found")
                
                # Step 7: Wait based on mode
                await asyncio.sleep(5.0 if self.bot_mode == 'HIGH_LATENCY' else 1.0)
        
        except KeyboardInterrupt:
            logging.info("🛑 Bot stopped by user")
        
        except Exception as e:
            logging.error(f"❌ Error in main loop: {e}", exc_info=True)
        
        finally:
            await self.data_feed.stop()
    
    async def get_exchange_wrappers(self):
        """Get wrapped exchange objects with balances"""
        exchange_wrappers = {}
        
        for exch_name, exchange in self.exchanges.items():
            try:
                balance = exchange.fetch_balance()
                
                class ExchangeWrapper:
                    def __init__(self, name, exchange_obj, balance_data):
                        self.name = name
                        self.exchange = exchange_obj
                        self.balances = {}
                        self.free_balances = {}
                        
                        # Extract all balances
                        for currency in ['BTC', 'USDT', 'USDC', 'USD']:
                            total = balance_data.get('total', {}).get(currency, 0)
                            free = balance_data.get('free', {}).get(currency, 0)
                            
                            if total > 0 or free > 0:
                                self.balances[currency] = total
                                self.free_balances[currency] = free
                
                wrapper = ExchangeWrapper(exch_name, exchange, balance)
                exchange_wrappers[exch_name] = wrapper
                
            except Exception as e:
                logging.error(f"❌ Error fetching balance for {exch_name}: {e}")
        
        return exchange_wrappers
    
    def calculate_available_stablecoins(self, exchange_wrappers):
        """Calculate total available stablecoins across all exchanges"""
        total = 0.0
        
        for wrapper in exchange_wrappers.values():
            for currency in ['USDT', 'USDC', 'USD']:
                if currency in wrapper.free_balances:
                    total += wrapper.free_balances[currency]
        
        return total
    
    def find_arbitrage_opportunities(self, price_data, symbols):
        """Find arbitrage opportunities across exchanges"""
        opportunities = []
        
        for symbol in symbols:
            if symbol in price_data and price_data[symbol]:
                symbol_data = price_data[symbol]
                
                if len(symbol_data) >= 2:
                    exchanges_with_prices = [
                        (name, data) for name, data in symbol_data.items() 
                        if data.get('ask') and data.get('bid')
                    ]
                    
                    if len(exchanges_with_prices) >= 2:
                        best_buy = min(exchanges_with_prices, key=lambda x: x[1]['ask'])
                        best_sell = max(exchanges_with_prices, key=lambda x: x[1]['bid'])
                        
                        if best_buy[0] != best_sell[0]:
                            spread = best_sell[1]['bid'] - best_buy[1]['ask']
                            spread_pct = (spread / best_buy[1]['ask']) * 100 if best_buy[1]['ask'] > 0 else 0
                            
                            if spread_pct > 0.5:
                                opportunity = {
                                    'symbol': symbol,
                                    'buy_exchange': best_buy[0],
                                    'sell_exchange': best_sell[0],
                                    'buy_price': best_buy[1]['ask'],
                                    'sell_price': best_sell[1]['bid'],
                                    'spread': spread,
                                    'spread_percentage': spread_pct,
                                    'amount': self.settings['position_size'] / best_buy[1]['ask']
                                }
                                
                                if opportunity['amount'] >= self.settings['min_trade_amount']:
                                    opportunities.append(opportunity)
                                    logging.info(
                                        f"🔍 Found opportunity: Buy {symbol} on {best_buy[0]} at ${best_buy[1]['ask']:.2f}, "
                                        f"sell on {best_sell[0]} at ${best_sell[1]['bid']:.2f} "
                                        f"(Spread: ${spread:.2f}, {spread_pct:.2f}%)"
                                    )
        
        return opportunities
    
    def run(self):
        """Run the bot"""
        asyncio.run(self.run_async())

if __name__ == "__main__":
    bot = ArbitrageBot()
    bot.run()