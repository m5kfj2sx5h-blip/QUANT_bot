import asyncio
import ccxt.pro as ccxtpro
import ccxt
import logging
import time
import json
from typing import Dict, List, Optional, Any
from exchanges_websocket import BinanceUSWebSocket, KrakenWebSocket, CoinbaseWebSocket
from market_context import MarketContext, AuctionState, MarketPhase, MacroSignal
from auction_context_module import AuctionContextModule

logger = logging.getLogger(__name__)

class DataFeed:
    def __init__(self, exchanges: Dict):
        self.exchanges = exchanges
        self.price_data = {}
        self.market_contexts = {}  # symbol -> MarketContext
        self.auction_analyzer = AuctionContextModule()
        
    async def start(self):
        raise NotImplementedError
        
    async def stop(self):
        raise NotImplementedError
        
    async def get_prices(self, symbols: List[str]) -> Dict:
        raise NotImplementedError
        
    def update_market_context(self, symbol: str, exchange: str, bids: List, asks: List, last_price: float):
        """Update market context with new order book data"""
        try:
            if symbol not in self.market_contexts:
                self.market_contexts[symbol] = MarketContext(primary_symbol=symbol)
            
            context = self.market_contexts[symbol]
            context.timestamp = time.time()
            
            # Update auction context
            context = self.auction_analyzer.analyze_order_book(bids, asks, last_price, context)
            
            # Update market phase based on auction state
            self._update_market_phase(context)
            
            # Update execution confidence
            self._update_execution_confidence(context)
            
            # Log significant context changes
            if context.auction_state != AuctionState.BALANCED:
                logger.debug(f"Market Context [{symbol}]: {context.to_dict()}")
                
        except Exception as e:
            logger.error(f"Error updating market context: {e}")


    def _update_market_phase(self, context: MarketContext):
        """Update market phase based on auction analysis"""
        if context.auction_state == AuctionState.IMBALANCED_BUYING:
            context.market_phase = MarketPhase.ACCUMULATION
            context.market_sentiment = 0.8
        elif context.auction_state == AuctionState.IMBALANCED_SELLING:
            context.market_phase = MarketPhase.DISTRIBUTION
            context.market_sentiment = -0.8
        elif context.auction_state == AuctionState.ACCEPTING:
            context.market_phase = MarketPhase.MARKUP
            context.market_sentiment = 0.5
        elif context.auction_state == AuctionState.REJECTING:
            context.market_phase = MarketPhase.MARKDOWN
            context.market_sentiment = -0.5
        else:
            context.market_phase = MarketPhase.UNKNOWN
            context.market_sentiment = 0.0


    def _update_execution_confidence(self, context: MarketContext):
        """Update execution confidence based on market conditions"""
        # Higher confidence when there's clear auction direction
        if context.auction_state in [AuctionState.IMBALANCED_BUYING, AuctionState.IMBALANCED_SELLING]:
            context.execution_confidence = 0.9
        elif context.auction_state in [AuctionState.ACCEPTING, AuctionState.REJECTING]:
            context.execution_confidence = 0.7
        elif context.auction_state == AuctionState.BALANCED:
            context.execution_confidence = 0.5
        else:
            context.execution_confidence = 0.3
            
        # Adjust based on sentiment strength
        context.execution_confidence *= (1.0 + abs(context.market_sentiment))


class WebSocketFeed(DataFeed):
    def __init__(self, exchanges: Dict):
        super().__init__(exchanges)
        self.running = False
        self.ws_connections = {}
        self.pro_exchanges = {}
        
    async def start(self):
        """Start WebSocket connections with proper authentication"""
        logger.info("🔌 Starting LOW-LATENCY WebSocket data feed with authentication")
        
        try:
            # Initialize ccxt.pro exchanges with authentication
            await self._init_pro_exchanges()
            
            # Also initialize custom WebSocket connections for redundancy
            await self._init_custom_websockets()
            
            self.running = True
            
            # Start watching order books
            asyncio.create_task(self._watch_pro_orderbooks())
            
        except Exception as e:
            logger.error(f"Failed to start WebSocket feed: {e}")
            # Fall back to custom WebSockets if ccxt.pro fails
            await self._fallback_to_custom_websockets()
            
    async def _init_pro_exchanges(self):
        """Initialize authenticated ccxt.pro exchanges"""
        for name, exch in self.exchanges.items():
            try:
                # Create ccxt.pro exchange with same config
                if name == 'kraken':
                    pro_config = {
                        'apiKey': exch.apiKey,
                        'secret': exch.secret,
                        'enableRateLimit': True,
                        'nonce': lambda: int(time.time() * 1000),
                        'options': {'adjustForTimeDifference': True}
                    }
                    self.pro_exchanges[name] = ccxtpro.kraken(pro_config)
                    
                elif name == 'binance':
                    pro_config = {
                        'apiKey': exch.apiKey,
                        'secret': exch.secret,
                        'enableRateLimit': True
                    }
                    self.pro_exchanges[name] = ccxtpro.binanceus(pro_config)
                    
                elif name == 'coinbase':
                    pro_config = {
                        'apiKey': exch.apiKey,
                        'secret': exch.secret,
                        'enableRateLimit': True
                    }
                    self.pro_exchanges[name] = ccxtpro.coinbase(pro_config)
                
                # Load markets for pro exchange
                await self.pro_exchanges[name].load_markets()
                logger.info(f"✅ ccxt.pro {name.upper()} initialized")
                
            except Exception as e:
                logger.error(f"❌ Failed to init ccxt.pro {name}: {e}")
                
    async def _init_custom_websockets(self):
        """Initialize custom WebSocket connections"""
        try:
            # Binance
            binance_ws = BinanceUSWebSocket("btcusdt")
            await binance_ws.connect()
            binance_ws.subscribe(self._handle_websocket_data)
            self.ws_connections['binance'] = binance_ws
            
            # Kraken
            kraken_ws = KrakenWebSocket("XBT/USD")
            await kraken_ws.connect()
            kraken_ws.subscribe(self._handle_websocket_data)
            self.ws_connections['kraken'] = kraken_ws
            
            # Coinbase
            coinbase_ws = CoinbaseWebSocket("BTC-USD")
            await coinbase_ws.connect()
            coinbase_ws.subscribe(self._handle_websocket_data)
            self.ws_connections['coinbase'] = coinbase_ws
            
            logger.info("✅ Custom WebSocket connections established")
            
        except Exception as e:
            logger.error(f"❌ Custom WebSocket init failed: {e}")
            
    async def _handle_websocket_data(self, data: Dict):
        """Handle incoming WebSocket data from custom connections"""
        try:
            exchange = data.get('exchange', '')
            data_type = data.get('type', '')
            
            if data_type == 'orderbook':
                # Map exchange names
                if exchange == 'binance_us':
                    exchange = 'binance'
                    symbol = 'BTC/USDT'
                elif exchange == 'kraken':
                    symbol = 'BTC/USD'
                elif exchange == 'coinbase':
                    symbol = 'BTC/USD'
                else:
                    return
                
                # Extract best bid/ask
                bids = data.get('bids', [])
                asks = data.get('asks', [])
                
                if bids and asks:
                    best_bid = float(bids[0][0]) if bids[0] else None
                    best_ask = float(asks[0][0]) if asks[0] else None
                    
                    if best_bid and best_ask:
                        # Update price data
                        if symbol not in self.price_data:
                            self.price_data[symbol] = {}
                        
                        self.price_data[symbol][exchange] = {
                            'bid': best_bid,
                            'ask': best_ask,
                            'bids': bids[:5],  # Top 5 bids for context
                            'asks': asks[:5],  # Top 5 asks for context
                            'timestamp': data.get('timestamp', time.time())
                        }
                        
                        # Update market context
                        last_price = (best_bid + best_ask) / 2
                        self.update_market_context(symbol, exchange, bids, asks, last_price)
                        
        except Exception as e:
            logger.error(f"WebSocket data handling error: {e}")
            
    async def _watch_pro_orderbooks(self):
        """Watch order books using ccxt.pro"""
        tasks = []
        
        for name, pro_exch in self.pro_exchanges.items():
            # Determine symbols to watch for this exchange
            symbols = []
            if 'BTC/USDT' in pro_exch.markets:
                symbols.append('BTC/USDT')
            if 'BTC/USDC' in pro_exch.markets:
                symbols.append('BTC/USDC')
            if 'BTC/USD' in pro_exch.markets:
                symbols.append('BTC/USD')
            
            for symbol in symbols:
                if symbol in pro_exch.markets:
                    tasks.append(self._watch_single_book(name, pro_exch, symbol))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    async def _watch_single_book(self, exch_name: str, exchange, symbol: str):
        """Watch a single order book"""
        while self.running:
            try:
                orderbook = await exchange.watch_order_book(symbol)
                
                if symbol not in self.price_data:
                    self.price_data[symbol] = {}
                
                # Extract best bid/ask
                best_bid = orderbook['bids'][0][0] if orderbook['bids'] else None
                best_ask = orderbook['asks'][0][0] if orderbook['asks'] else None
                
                if best_bid and best_ask:
                    self.price_data[symbol][exch_name] = {
                        'bid': best_bid,
                        'ask': best_ask,
                        'bids': orderbook['bids'][:5],
                        'asks': orderbook['asks'][:5],
                        'timestamp': orderbook['timestamp']
                    }
                    
                    # Update market context
                    last_price = (best_bid + best_ask) / 2
                    self.update_market_context(
                        symbol, 
                        exch_name, 
                        orderbook['bids'][:10], 
                        orderbook['asks'][:10], 
                        last_price
                    )
                
                # Small sleep to prevent overwhelming
                await exchange.sleep(0.01)
                
            except Exception as e:
                logger.error(f"ccxt.pro WebSocket error on {exch_name} {symbol}: {e}")
                await asyncio.sleep(5)
                
    async def _fallback_to_custom_websockets(self):
        """Fall back to using only custom WebSockets"""
        logger.warning("🔄 Falling back to custom WebSocket connections")
        self.running = True
        
        # Poll custom connections for data
        while self.running:
            await asyncio.sleep(0.1)
            
    async def get_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get current prices for requested symbols"""
        result = {}
        
        for symbol in symbols:
            if symbol in self.price_data:
                result[symbol] = self.price_data[symbol].copy()
            else:
                result[symbol] = {}
        
        return result
        
    async def stop(self):
        """Stop all WebSocket connections"""
        logger.info("🛑 Stopping WebSocket feed")
        self.running = False
        
        # Close ccxt.pro exchanges
        for name, exch in self.pro_exchanges.items():
            try:
                await exch.close()
            except:
                pass
                
        # Close custom WebSocket connections
        for name, ws in self.ws_connections.items():
            try:
                await ws.ws.close()
            except:
                pass
                
        logger.info("✅ WebSocket feed stopped")


class RESTPollingFeed(DataFeed):
    def __init__(self, exchanges: Dict):
        super().__init__(exchanges)
        self.price_data = {}
        
    async def start(self):
        """Start REST polling feed"""
        logger.info("🔌 Starting HIGH-LATENCY REST polling data feed")
        
    async def get_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """Poll exchanges for ticker data"""
        import concurrent.futures
        
        def fetch_ticker(args):
            name, exchange, symbol = args
            try:
                ticker = exchange.fetch_ticker(symbol)
                return (name, symbol, ticker['bid'], ticker['ask'], ticker['last'])
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol} from {name}: {e}")
                return (name, symbol, None, None, None)
        
        # Prepare tasks
        tasks = []
        for name, exchange in self.exchanges.items():
            for symbol in symbols:
                if symbol in exchange.markets:
                    tasks.append((name, exchange, symbol))
        
        # Use ThreadPoolExecutor for concurrent polling
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            results = list(executor.map(fetch_ticker, tasks))
        
        # Process results
        for name, symbol, bid, ask, last in results:
            if symbol not in self.price_data:
                self.price_data[symbol] = {}
            
            if bid and ask:
                self.price_data[symbol][name] = {
                    'bid': bid,
                    'ask': ask,
                    'timestamp': time.time()
                }
                
                # Create simulated order book for market context
                simulated_bids = [[bid * 0.999, 1.0], [bid * 0.998, 2.0], [bid * 0.997, 0.5]]
                simulated_asks = [[ask * 1.001, 1.0], [ask * 1.002, 2.0], [ask * 1.003, 0.5]]
                
                # Update market context
                self.update_market_context(symbol, name, simulated_bids, simulated_asks, last or bid)
        
        return self.price_data.copy()
        
    async def stop(self):
        """Stop REST polling feed"""
        logger.info("🛑 Stopping REST polling feed")