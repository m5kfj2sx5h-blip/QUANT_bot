import asyncio
import logging
import time
import ccxt
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Tuple, Optional
import json

logger = logging.getLogger(__name__)

class SmartOrderChaser:
    def __init__(self, fee_manager):
        self.fee_manager = fee_manager
        self.max_attempts = 3
        self.initial_wait = 0.1
        self.price_adjustment_pct = 0.0002
        
    def execute_order(self, exchange, symbol: str, side: str, amount: float, order_type: str = 'limit') -> Optional[Dict]:
        """Execute order with exchange-specific handling"""
        exchange_name = exchange.id.lower()
        
        try:
            # Get market info for validation
            market = exchange.market(symbol)
            min_amount = market.get('limits', {}).get('amount', {}).get('min', 0.0001)
            
            # Validate minimum amount
            if amount < min_amount:
                logger.warning(f"Amount {amount} below minimum {min_amount} for {symbol}")
                return None
            
            # Execute based on order type
            if order_type == 'market':
                return self._execute_market_order(exchange, symbol, side, amount, exchange_name)
            else:
                return self._execute_limit_order(exchange, symbol, side, amount, exchange_name)
                
        except Exception as e:
            logger.error(f"Order execution failed: {e}")
            return None
    
    def _execute_market_order(self, exchange, symbol: str, side: str, amount: float, exchange_name: str) -> Optional[Dict]:
        """Execute market order with exchange-specific handling"""
        try:
            if 'coinbase' in exchange_name and side == 'buy':
                # Coinbase requires special handling for market buys
                # For market buys, we need to specify cost (amount * price)
                ticker = exchange.fetch_ticker(symbol)
                price = ticker['ask'] * 1.005  # Slight premium to ensure execution
                
                # Calculate cost (amount to spend in quote currency)
                cost = amount * price
                
                # Create market buy with cost parameter
                order = exchange.create_market_order(
                    symbol, 
                    side, 
                    amount, 
                    params={'createMarketBuyOrderRequiresPrice': False, 'cost': cost}
                )
                logger.info(f"Coinbase market BUY: {order.get('id', 'N/A')} for ${cost:.2f}")
                
            elif 'coinbase' in exchange_name and side == 'sell':
                # For Coinbase market sells, we can use regular market order
                order = exchange.create_market_order(symbol, side, amount)
                logger.info(f"Coinbase market SELL: {order.get('id', 'N/A')} of {amount}")
                
            else:
                # Standard market order for other exchanges
                order = exchange.create_market_order(symbol, side, amount)
                logger.info(f"Market {side.upper()}: {order.get('id', 'N/A')} of {amount}")
            
            return order
            
        except ccxt.InsufficientFunds as e:
            logger.error(f"Insufficient funds for market {side}: {e}")
            return None
        except Exception as e:
            logger.error(f"Market order failed: {e}")
            return None
    
    def _execute_limit_order(self, exchange, symbol: str, side: str, amount: float, exchange_name: str) -> Optional[Dict]:
        """Execute limit order with chasing"""
        for attempt in range(self.max_attempts):
            try:
                # Get current market price
                ticker = exchange.fetch_ticker(symbol)
                
                if side == 'buy':
                    price = ticker['ask']
                    # For buys, we add a small premium to get filled
                    if attempt > 0:
                        price = price * (1 + (self.price_adjustment_pct * attempt))
                else:
                    price = ticker['bid']
                    # For sells, we reduce price slightly to get filled
                    if attempt > 0:
                        price = price * (1 - (self.price_adjustment_pct * attempt))
                
                # Round price appropriately
                price = float(Decimal(str(price)).quantize(Decimal('0.01'), rounding=ROUND_DOWN))
                
                # Place limit order
                order = exchange.create_limit_order(symbol, side, amount, price)
                logger.info(f"Limit {side.upper()}: {order.get('id', 'N/A')} at ${price:.2f} for {amount}")
                
                return order
                
            except ccxt.InsufficientFunds as e:
                logger.error(f"Insufficient funds on attempt {attempt+1}: {e}")
                return None
            except ccxt.NetworkError as e:
                logger.warning(f"Network error on attempt {attempt+1}: {e}")
                time.sleep(self.initial_wait * (attempt + 1))
            except Exception as e:
                logger.error(f"Limit order failed on attempt {attempt+1}: {e}")
                time.sleep(self.initial_wait * (attempt + 1))
        
        logger.error(f"All limit order attempts failed for {side} {amount} {symbol}")
        return None


class PortfolioState:
    """Track portfolio state to avoid repeated insufficient funds errors"""
    
    def __init__(self):
        self.used_funds = {}  # exchange -> {currency: amount_used}
        self.executed_trades = []
        self.last_update = time.time()
    
    def reset_used_funds(self):
        """Reset used funds tracker"""
        self.used_funds = {}
        self.last_update = time.time()
    
    def mark_funds_used(self, exchange_name: str, currency: str, amount: float):
        """Mark funds as used on an exchange"""
        if exchange_name not in self.used_funds:
            self.used_funds[exchange_name] = {}
        
        if currency not in self.used_funds[exchange_name]:
            self.used_funds[exchange_name][currency] = 0
        
        self.used_funds[exchange_name][currency] += amount
        self.executed_trades.append({
            'time': time.time(),
            'exchange': exchange_name,
            'currency': currency,
            'amount': amount
        })
    
    def get_available_funds(self, exchange_wrapper, currency: str) -> float:
        """Get available funds considering what's already been used"""
        exchange_name = exchange_wrapper.name
        
        # Get free balance from wrapper
        free_balance = exchange_wrapper.free_balances.get(currency, 0)
        
        # Subtract used funds
        used = self.used_funds.get(exchange_name, {}).get(currency, 0)
        
        available = max(0, free_balance - used)
        return available


class OrderExecutor:
    def __init__(self, fee_manager):
        self.fee_manager = fee_manager
        self.portfolio_state = PortfolioState()
        self.order_chaser = SmartOrderChaser(fee_manager)
    
    async def execute_arbitrage(self, opportunity: Dict, exchanges: Dict) -> bool:
        """Execute arbitrage trade between exchanges"""
        raise NotImplementedError("Subclasses must implement execute_arbitrage")
    
    async def execute_rebalancing(self, exchange_wrappers: Dict, exchanges: Dict, 
                                  price_data: Dict, settings: Dict) -> bool:
        """
        Execute portfolio rebalancing by buying BTC with stablecoins.
        This is the INITIAL step to get BTC for arbitrage.
        """
        logger.info("🔄 EXECUTING PORTFOLIO REBALANCE: Buying BTC with stablecoins")
        
        # Reset used funds tracker for new rebalance cycle
        self.portfolio_state.reset_used_funds()
        
        # Step 1: Calculate total available stablecoins
        stablecoin_allocation = self._calculate_stablecoin_allocation(exchange_wrappers)
        total_stable_value = sum(stablecoin_allocation.values())
        
        if total_stable_value < settings['min_order_value']:
            logger.info(f"💰 Insufficient stablecoins: ${total_stable_value:.2f} (min: ${settings['min_order_value']})")
            return False
        
        logger.info(f"💰 Available stablecoins: ${total_stable_value:.2f}")
        for currency, amount in stablecoin_allocation.items():
            if amount > 0:
                logger.info(f"   {currency}: ${amount:.2f}")
        
        # Step 2: Determine how much BTC to buy (use 80% of available stablecoins)
        btc_to_buy_value = total_stable_value * 0.8
        logger.info(f"📊 Will use ${btc_to_buy_value:.2f} to buy BTC")
        
        # Step 3: Execute BTC purchases
        executed_trades = []
        remaining_value = btc_to_buy_value
        
        # Sort stablecoins by amount (largest first)
        sorted_stablecoins = sorted(
            stablecoin_allocation.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        for currency, available_value in sorted_stablecoins:
            if remaining_value <= 0:
                break
            
            # Determine how much of this stablecoin to use
            use_value = min(available_value, remaining_value)
            if use_value < settings['min_order_value']:
                continue
            
            # Buy BTC with this stablecoin
            trades = await self._buy_btc_with_stablecoin(
                exchange_wrappers,
                exchanges,
                price_data,
                currency,
                use_value,
                settings
            )
            
            executed_trades.extend(trades)
            
            # Update remaining value
            if trades:
                remaining_value -= use_value
        
        # Step 4: Log results
        if executed_trades:
            logger.info(f"✅ REBALANCING COMPLETE: Executed {len(executed_trades)} trades")
            
            # Log trade summary
            total_btc_bought = sum(t.get('btc_amount', 0) for t in executed_trades)
            total_spent = sum(t.get('cost', 0) for t in executed_trades)
            
            logger.info(f"📈 Summary: Bought {total_btc_bought:.6f} BTC for ${total_spent:.2f}")
            
            # Save execution state
            self._save_rebalance_state(executed_trades)
            return True
        else:
            logger.warning("⚠️ REBALANCING FAILED: No trades executed")
            return False
    
    def _calculate_stablecoin_allocation(self, exchange_wrappers: Dict) -> Dict:
        """Calculate available stablecoins across all exchanges"""
        stablecoins = {}
        
        for wrapper in exchange_wrappers.values():
            for currency in ['USDT', 'USDC', 'USD']:
                if currency in wrapper.free_balances:
                    amount = wrapper.free_balances[currency]
                    if amount > 0:
                        if currency not in stablecoins:
                            stablecoins[currency] = 0
                        stablecoins[currency] += amount
        
        return stablecoins
    
    async def _buy_btc_with_stablecoin(self, exchange_wrappers: Dict, exchanges: Dict,
                                      price_data: Dict, currency: str, 
                                      use_value: float, settings: Dict) -> List[Dict]:
        """
        Buy BTC with a specific stablecoin across available exchanges
        """
        trades = []
        
        # Determine symbol based on currency
        if currency == 'USD':
            symbol = 'BTC/USDT'  # Most exchanges don't have BTC/USD
            target_currency = 'USDT'
        else:
            symbol = f'BTC/{currency}'
            target_currency = currency
        
        logger.info(f"   Buying BTC with {currency}, target: ${use_value:.2f}")
        
        # Find exchanges that have this pair and available funds
        for wrapper in exchange_wrappers.values():
            if target_currency not in wrapper.free_balances:
                continue
            
            # Check available funds (considering already used)
            available_funds = self.portfolio_state.get_available_funds(wrapper, target_currency)
            
            if available_funds <= 0:
                continue
            
            # Determine how much to use from this exchange
            exchange_use_value = min(use_value, available_funds)
            if exchange_use_value < settings['min_order_value']:
                continue
            
            # Get best price for this exchange
            exchange_name = wrapper.name
            current_price = self._get_best_price(exchange_name, symbol, price_data, 'buy')
            
            if not current_price:
                logger.warning(f"      No price data for {symbol} on {exchange_name}")
                continue
            
            # Calculate BTC amount to buy
            btc_amount = exchange_use_value / current_price
            
            # Check minimum trade amount
            if btc_amount < settings['min_trade_amount']:
                logger.warning(f"      BTC amount {btc_amount:.6f} below minimum {settings['min_trade_amount']}")
                continue
            
            # Execute trade
            trade_result = await self._execute_btc_purchase(
                wrapper.exchange,
                symbol,
                btc_amount,
                exchange_use_value,
                exchange_name
            )
            
            if trade_result:
                trades.append(trade_result)
                # Mark funds as used
                self.portfolio_state.mark_funds_used(exchange_name, target_currency, exchange_use_value)
                
                # Update remaining use_value
                use_value -= exchange_use_value
                if use_value <= 0:
                    break
        
        return trades
    
    def _get_best_price(self, exchange_name: str, symbol: str, price_data: Dict, side: str) -> Optional[float]:
        """Get best available price for a symbol on an exchange"""
        if symbol not in price_data:
            return None
        
        exchange_data = price_data[symbol].get(exchange_name)
        if not exchange_data:
            return None
        
        if side == 'buy':
            return exchange_data.get('ask')
        else:
            return exchange_data.get('bid')
    
    async def _execute_btc_purchase(self, exchange, symbol: str, btc_amount: float,
                                   cost: float, exchange_name: str) -> Optional[Dict]:
        """Execute BTC purchase order"""
        try:
            logger.info(f"      💸 Buying {btc_amount:.6f} BTC on {exchange_name} for ${cost:.2f}")
            
            # For large purchases, use limit orders for better execution
            if cost > 1000:
                order_type = 'limit'
            else:
                order_type = 'market'
            
            order = self.order_chaser.execute_order(
                exchange,
                symbol,
                'buy',
                btc_amount,
                order_type
            )
            
            if order:
                logger.info(f"      ✅ BOUGHT {btc_amount:.6f} BTC on {exchange_name}")
                logger.info(f"         Order ID: {order.get('id', 'N/A')}")
                
                return {
                    'exchange': exchange_name,
                    'symbol': symbol,
                    'side': 'buy',
                    'btc_amount': btc_amount,
                    'cost': cost,
                    'order_id': order.get('id'),
                    'timestamp': time.time()
                }
            else:
                logger.warning(f"      ❌ Purchase failed on {exchange_name}")
                return None
                
        except Exception as e:
            logger.error(f"      ❌ BTC purchase error on {exchange_name}: {e}")
            return None
    
    def _save_rebalance_state(self, executed_trades: List[Dict]):
        """Save rebalance execution state for reference"""
        try:
            state = {
                'timestamp': time.time(),
                'trades': executed_trades,
                'total_btc': sum(t.get('btc_amount', 0) for t in executed_trades),
                'total_cost': sum(t.get('cost', 0) for t in executed_trades)
            }
            
            with open('rebalance_state.json', 'w') as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Could not save rebalance state: {e}")


class LowLatencyExecutor(OrderExecutor):
    def __init__(self, fee_manager):
        super().__init__(fee_manager)
        self.max_attempts = 1
        self.price_aggressiveness = 0.0001
    
    async def execute_arbitrage(self, opportunity: Dict, exchanges: Dict) -> bool:
        """Execute low-latency arbitrage trades"""
        logger.info(f"⚡ EXECUTING LOW-LATENCY ARBITRAGE")
        logger.info(f"   Buy: {opportunity['amount']:.6f} {opportunity['symbol']} on {opportunity['buy_exchange']} at ${opportunity['buy_price']:.2f}")
        logger.info(f"   Sell: {opportunity['amount']:.6f} {opportunity['symbol']} on {opportunity['sell_exchange']} at ${opportunity['sell_price']:.2f}")
        
        buy_exchange = exchanges.get(opportunity['buy_exchange'])
        sell_exchange = exchanges.get(opportunity['sell_exchange'])
        
        if not buy_exchange or not sell_exchange:
            logger.error("❌ Invalid exchange references")
            return False
        
        try:
            # Execute buy order
            buy_order = self.order_chaser.execute_order(
                buy_exchange,
                opportunity['symbol'],
                'buy',
                opportunity['amount'],
                'limit'
            )
            
            if not buy_order:
                logger.error("❌ Buy order failed")
                return False
            
            logger.info(f"  📥 BUY order placed: {buy_order.get('id', 'N/A')}")
            
            # Small delay for low-latency mode
            await asyncio.sleep(0.05)
            
            # Execute sell order
            sell_order = self.order_chaser.execute_order(
                sell_exchange,
                opportunity['symbol'],
                'sell',
                opportunity['amount'],
                'limit'
            )
            
            if not sell_order:
                logger.error("❌ Sell order failed")
                # Try to cancel buy order if sell fails
                try:
                    buy_exchange.cancel_order(buy_order['id'], opportunity['symbol'])
                    logger.info("  📝 Buy order cancelled")
                except:
                    pass
                return False
            
            logger.info(f"  📤 SELL order placed: {sell_order.get('id', 'N/A')}")
            logger.info("✅ ARBITRAGE EXECUTED")
            
            # Calculate estimated profit
            spread = opportunity['sell_price'] - opportunity['buy_price']
            estimated_profit = spread * opportunity['amount']
            logger.info(f"   Estimated profit: ${estimated_profit:.2f}")
            
            return True
            
        except ccxt.InsufficientFunds as e:
            logger.error(f"❌ Insufficient funds: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Arbitrage failed: {e}")
            return False


class HighLatencyExecutor(OrderExecutor):
    def __init__(self, fee_manager):
        super().__init__(fee_manager)
        self.max_attempts = 3
        self.price_adjustment = 0.0005
    
    async def execute_arbitrage(self, opportunity: Dict, exchanges: Dict) -> bool:
        """Execute high-latency arbitrage with order chasing"""
        logger.info(f"🐢 EXECUTING HIGH-LATENCY ARBITRAGE")
        logger.info(f"   Opportunity: {opportunity['spread_percentage']:.2f}% spread")
        
        buy_exchange = exchanges.get(opportunity['buy_exchange'])
        sell_exchange = exchanges.get(opportunity['sell_exchange'])
        
        if not buy_exchange or not sell_exchange:
            logger.error("❌ Invalid exchange references")
            return False
        
        success = False
        
        for attempt in range(self.max_attempts):
            try:
                logger.info(f"  🔄 Attempt {attempt + 1}/{self.max_attempts}")
                
                # Adjust price based on attempt
                adjusted_buy_price = opportunity['buy_price'] * (1 - (self.price_adjustment * attempt))
                adjusted_sell_price = opportunity['sell_price'] * (1 + (self.price_adjustment * attempt))
                
                # Execute buy with adjusted price
                buy_order = buy_exchange.create_limit_order(
                    opportunity['symbol'],
                    'buy',
                    opportunity['amount'],
                    adjusted_buy_price
                )
                
                if not buy_order:
                    logger.warning(f"  ⚠️ Buy order failed on attempt {attempt + 1}")
                    await asyncio.sleep(2 ** attempt)
                    continue
                
                logger.info(f"  📥 BUY placed at ${adjusted_buy_price:.2f}")
                
                # Longer delay for high-latency mode
                await asyncio.sleep(1)
                
                # Execute sell with adjusted price
                sell_order = sell_exchange.create_limit_order(
                    opportunity['symbol'],
                    'sell',
                    opportunity['amount'],
                    adjusted_sell_price
                )
                
                if sell_order:
                    logger.info(f"  📤 SELL placed at ${adjusted_sell_price:.2f}")
                    logger.info(f"✅ ARBITRAGE SUCCEEDED on attempt {attempt + 1}")
                    
                    # Calculate estimated profit
                    spread = adjusted_sell_price - adjusted_buy_price
                    estimated_profit = spread * opportunity['amount']
                    logger.info(f"   Estimated profit: ${estimated_profit:.2f}")
                    
                    success = True
                    break
                else:
                    logger.warning(f"  ⚠️ Sell order failed, cancelling buy")
                    
                    # Cancel buy order if sell fails
                    try:
                        buy_exchange.cancel_order(buy_order['id'], opportunity['symbol'])
                        logger.info("  📝 Buy order cancelled")
                    except:
                        logger.warning("  ⚠️ Could not cancel buy order")
                    
                    await asyncio.sleep(2 ** attempt)
                    
            except ccxt.InsufficientFunds as e:
                logger.error(f"❌ Insufficient funds on attempt {attempt + 1}: {e}")
                break
            except Exception as e:
                logger.warning(f"  ⚠️ Attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(2 ** attempt)
        
        if not success:
            logger.error("❌ All arbitrage attempts failed")
        
        return success