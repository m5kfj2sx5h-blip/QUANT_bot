import logging
import json
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class RebalanceMonitor:
    def __init__(self, config_path='config/rebalance_config.json'):
        self.config_path = config_path
        self.TARGET_ALLOCATIONS = {
            'BTC': 0.50,
            'USDT': 0.25,
            'USDC': 0.25
        }
        self.REBALANCE_THRESHOLD = 0.05
        self.HYBRID_STRATEGY = True
        self.STATIC_TARGETS = {'BTC': 0.5, 'USDT': 0.25, 'USDC': 0.25}
        self.last_rebalance_time = None
        self.MIN_REBALANCE_AMOUNT_USD = 10.0
        self._load_config()
        logger.info(f"⚖️ Rebalance Monitor Initialized. Mode: {'Hybrid' if self.HYBRID_STRATEGY else 'Static'}. Targets: {self.TARGET_ALLOCATIONS}")

    def _load_config(self):
        default_config = {
            "target_allocations": self.TARGET_ALLOCATIONS,
            "rebalance_threshold": self.REBALANCE_THRESHOLD,
            "hybrid_strategy": self.HYBRID_STRATEGY,
            "static_targets": self.STATIC_TARGETS,
            "min_rebalance_amount_usd": self.MIN_REBALANCE_AMOUNT_USD
        }
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)
                    self.TARGET_ALLOCATIONS = loaded_config.get("target_allocations", self.TARGET_ALLOCATIONS)
                    self.REBALANCE_THRESHOLD = loaded_config.get("rebalance_threshold", self.REBALANCE_THRESHOLD)
                    self.HYBRID_STRATEGY = loaded_config.get("hybrid_strategy", self.HYBRID_STRATEGY)
                    self.STATIC_TARGETS = loaded_config.get("static_targets", self.STATIC_TARGETS)
                    self.MIN_REBALANCE_AMOUNT_USD = loaded_config.get("min_rebalance_amount_usd", self.MIN_REBALANCE_AMOUNT_USD)
        except Exception as e:
            logger.error(f"Failed to load rebalance config: {e}. Using defaults.")

    def should_rebalance(self, exchange_wrappers, price_data):
        """Check if rebalancing is needed using exchange-specific prices"""
        try:
            if not price_data:
                logger.warning("⚠️ No price data available, skipping rebalance check")
                return False
                
            allocations = self._calculate_allocations(exchange_wrappers, price_data)
            
            if not allocations:
                logger.info("📊 No portfolio value to calculate allocations")
                return False
                
            logger.info(f"📊 Current Allocations: {allocations}")

            if self.HYBRID_STRATEGY:
                needs_rebalance = self._check_hybrid_rebalance(allocations, exchange_wrappers)
            else:
                needs_rebalance = self._check_static_rebalance(allocations)

            if needs_rebalance:
                logger.warning("⚠️ Rebalance required based on allocation thresholds.")
                return True
            return False
        except Exception as e:
            logger.error(f"Error in rebalance check: {e}", exc_info=True)
            return False

    def _calculate_allocations(self, exchange_wrappers, price_data):
        """Calculate current portfolio allocations using exchange-specific prices"""
        total_values = {}
        total_portfolio_value = 0.0

        for wrapper in exchange_wrappers.values():
            exchange_name = wrapper.name
            for currency, amount in wrapper.balances.items():
                if amount <= 0:
                    continue
                    
                if currency in ['USDT', 'USDC', 'USD']:
                    # Stablecoins are valued at 1:1
                    value = float(amount)
                    total_values[currency] = total_values.get(currency, 0.0) + value
                    total_portfolio_value += value
                    
                elif currency == 'BTC':
                    # Get BTC value for this exchange
                    btc_value = self._get_btc_value_for_exchange(exchange_name, amount, price_data)
                    if btc_value > 0:
                        total_values['BTC'] = total_values.get('BTC', 0.0) + btc_value
                        total_portfolio_value += btc_value

        if total_portfolio_value <= 0:
            return {}

        allocations = {}
        for asset, value in total_values.items():
            allocations[asset] = value / total_portfolio_value

        sorted_allocations = dict(sorted(allocations.items(), key=lambda x: x[1], reverse=True))
        return sorted_allocations

    def _get_btc_value_for_exchange(self, exchange_name, btc_amount, price_data):
        """Get BTC value for a specific exchange using available price data"""
        # Try different BTC pairs
        btc_pairs = ['BTC/USDT', 'BTC/USDC', 'BTC/USD']
        
        for pair in btc_pairs:
            if pair in price_data and exchange_name in price_data[pair]:
                price_info = price_data[pair][exchange_name]
                if 'bid' in price_info and price_info['bid']:
                    # Use bid price for valuation (conservative)
                    return float(btc_amount) * float(price_info['bid'])
        
        # If no specific price found, try to find any BTC price for this exchange
        for pair, exchanges in price_data.items():
            if 'BTC' in pair and exchange_name in exchanges:
                price_info = exchanges[exchange_name]
                if 'bid' in price_info and price_info['bid']:
                    return float(btc_amount) * float(price_info['bid'])
        
        logger.warning(f"⚠️ No BTC price found for {exchange_name}, using 0 value")
        return 0.0

    def _check_static_rebalance(self, allocations):
        """Check rebalance against static targets"""
        for asset, current_alloc in allocations.items():
            if asset in self.TARGET_ALLOCATIONS:
                target_alloc = self.TARGET_ALLOCATIONS[asset]
                diff = abs(current_alloc - target_alloc)
                if diff > self.REBALANCE_THRESHOLD:
                    logger.info(f"  {asset}: {current_alloc:.1%} vs target {target_alloc:.1%} (diff: {diff:.1%})")
                    return True
        return False

    def _check_hybrid_rebalance(self, allocations, exchange_wrappers):
        """Check rebalance using hybrid strategy"""
        btc_allocation = allocations.get('BTC', 0.0)
        target_btc = self.STATIC_TARGETS.get('BTC', 0.5)

        if btc_allocation < (target_btc - self.REBALANCE_THRESHOLD):
            logger.info(f"  BTC allocation low: {btc_allocation:.1%} < target {target_btc:.1%}")
            stable_balance = self._get_total_stable_balance(exchange_wrappers)
            if stable_balance > self.MIN_REBALANCE_AMOUNT_USD:
                return True
        elif btc_allocation > (target_btc + self.REBALANCE_THRESHOLD):
            logger.info(f"  BTC allocation high: {btc_allocation:.1%} > target {target_btc:.1%}")
            return True

        # Check for asset concentration
        if allocations:
            max_asset = max(allocations.items(), key=lambda x: x[1])
            if max_asset[1] > 0.65:
                logger.warning(f"  Asset concentration: {max_asset[0]} at {max_asset[1]:.1%}")
                return True

        return False

    def _get_total_stable_balance(self, exchange_wrappers):
        """Get total available stablecoins"""
        total_stable = 0.0
        for wrapper in exchange_wrappers.values():
            for currency in ['USDT', 'USDC', 'USD']:
                if currency in wrapper.free_balances:
                    total_stable += float(wrapper.free_balances[currency])
        return total_stable

    def generate_rebalance_plan(self, exchange_wrappers, price_data):
        """Generate rebalancing plan using exchange-specific prices"""
        try:
            allocations = self._calculate_allocations(exchange_wrappers, price_data)
            
            if not allocations:
                return {'buys': {}, 'sells': {}}
            
            # Calculate total portfolio value
            total_value = 0.0
            asset_values = {}
            
            for wrapper in exchange_wrappers.values():
                exchange_name = wrapper.name
                for currency, amount in wrapper.balances.items():
                    if amount > 0 and currency in ['BTC', 'USDT', 'USDC', 'USD']:
                        if currency == 'BTC':
                            value = self._get_btc_value_for_exchange(exchange_name, amount, price_data)
                        else:
                            value = float(amount)
                        
                        total_value += value
                        asset_values[currency] = asset_values.get(currency, 0.0) + value

            plan = {'buys': {}, 'sells': {}}
            
            for asset, current_value in asset_values.items():
                if asset in self.TARGET_ALLOCATIONS:
                    target_percent = self.TARGET_ALLOCATIONS[asset]
                    target_value = total_value * target_percent
                    difference = target_value - current_value

                    if abs(difference) >= self.MIN_REBALANCE_AMOUNT_USD:
                        if difference > 0:
                            plan['buys'][asset] = difference
                        else:
                            plan['sells'][asset] = abs(difference)

            logger.info(f"📋 Rebalance Plan: {plan}")
            return plan
            
        except Exception as e:
            logger.error(f"Failed to generate rebalance plan: {e}")
            return {'buys': {}, 'sells': {}}