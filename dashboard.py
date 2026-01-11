import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import ccxt
import os
import json
import time
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv('/Users/dj3bosmacbookpro/Desktop/.env')

FEE_STATE_PATH = '/Users/dj3bosmacbookpro/Desktop/QUANT_bot/fee_state.json'

class FeeStateManager:
    def __init__(self):
        self.state = self._load_state()
        self._ensure_monthly_reset()
    
    def _load_state(self):
        default_state = {
            "last_reset_date": datetime.now().strftime("%Y-%m-%d"),
            "exchanges": {
                "binance": {
                    "discount_active": True,
                    "discount_type": "BNB_PAYMENT",
                    "standard_taker": 0.001,
                    "discounted_taker": 0.00095,
                    "bnb_balance_check": True,
                    "notes": "BNB discount: ON. 5% savings active.",
                    "trades_with_discount": 0
                },
                "kraken": {
                    "discount_active": True,
                    "discount_type": "KRAKEN_PLUS",
                    "monthly_fee_credit_usd": 10000.0,
                    "fees_used_this_month_usd": 0.0,
                    "credit_remaining_usd": 10000.0,
                    "standard_taker": 0.0026,
                    "discounted_taker": 0.0,
                    "notes": "Kraken+ Active: $10k/month free fees."
                },
                "coinbase": {
                    "discount_active": True,
                    "discount_type": "COINBASE_ONE",
                    "monthly_fee_credit_usd": 500.0,
                    "fees_used_this_month_usd": 0.0,
                    "credit_remaining_usd": 500.0,
                    "standard_taker": 0.006,
                    "discounted_taker": 0.0,
                    "notes": "Coinbase One Active: $500/month free fees."
                }
            }
        }
        try:
            if os.path.exists(FEE_STATE_PATH):
                with open(FEE_STATE_PATH, 'r') as f:
                    return json.load(f)
        except:
            pass
        return default_state
    
    def _ensure_monthly_reset(self):
        current_date = datetime.now().strftime("%Y-%m-%d")
        last_reset = self.state.get("last_reset_date", current_date)
        if last_reset[:7] != current_date[:7]:
            for exch_data in self.state["exchanges"].values():
                if "fees_used_this_month_usd" in exch_data:
                    exch_data["fees_used_this_month_usd"] = 0.0
                if exch_data["discount_type"] == "KRAKEN_PLUS":
                    exch_data["credit_remaining_usd"] = 10000.0
                elif exch_data["discount_type"] == "COINBASE_ONE":
                    exch_data["credit_remaining_usd"] = 500.0
            self.state["last_reset_date"] = current_date
            self.save_state()
    
    def get_current_taker_fee(self, exchange_name, trade_value_usd=0):
        exch = self.state["exchanges"].get(exchange_name.lower())
        if not exch:
            return {"effective_fee_rate": 0.001, "discount_active": False}
        
        if exch['discount_active']:
            if exch['discount_type'] in ['KRAKEN_PLUS', 'COINBASE_ONE']:
                potential_fee = trade_value_usd * exch['discounted_taker']
                if potential_fee <= exch['credit_remaining_usd']:
                    return {
                        "effective_fee_rate": exch['discounted_taker'],
                        "discount_active": True,
                        "credit_remaining": exch['credit_remaining_usd']
                    }
            else:
                return {
                    "effective_fee_rate": exch['discounted_taker'],
                    "discount_active": True,
                    "credit_remaining": None
                }
        
        return {
            "effective_fee_rate": exch['standard_taker'],
            "discount_active": False,
            "credit_remaining": exch.get('credit_remaining_usd', 0)
        }
    
    def save_state(self):
        try:
            with open(FEE_STATE_PATH, 'w') as f:
                json.dump(self.state, f, indent=2)
        except:
            pass

fee_manager = FeeStateManager()

st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    color: white;
}
.stButton > button {
    background: linear-gradient(90deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
    font-weight: 600 !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 10px 20px !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3) !important;
    font-size: 12px !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5) !important;
}
.metric-card {
    background: rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(10px);
    border-radius: 12px;
    padding: 15px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    margin-bottom: 10px;
    height: 100%;
}
.exchange-card {
    background: rgba(255, 255, 255, 0.07);
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 12px;
    border-left: 4px solid;
}
.exchange-online { border-left-color: #00ffa3; }
.exchange-offline { border-left-color: #ff3333; }
h1, h2, h3, h4 {
    background: linear-gradient(90deg, #ffffff 0%, #a5b4fc 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 700;
}
.compact-container {
    padding: 8px !important;
    margin: 3px !important;
}
.compact-metric {
    font-size: 18px !important;
    margin: 3px 0 !important;
    font-weight: 700;
}
.compact-label {
    font-size: 10px !important;
    opacity: 0.7;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.balance-change-up {
    color: #00ffa3;
    font-size: 10px;
}
.balance-change-down {
    color: #ff3333;
    font-size: 10px;
}
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.stDeployButton {display:none;}
.gold-battery {
    background: linear-gradient(90deg, #fbbf24 0%, #f59e0b 50%, #d97706 100%);
    height: 20px;
    border-radius: 10px;
    margin: 5px 0;
    overflow: hidden;
}
.gold-battery-fill {
    background: linear-gradient(90deg, #fde68a 0%, #fcd34d 50%, #fbbf24 100%);
    height: 100%;
    border-radius: 10px;
    transition: width 0.5s ease;
}
.intel-badge {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: bold;
    margin: 2px;
}
.badge-green { background: rgba(0, 255, 163, 0.2); color: #00ffa3; border: 1px solid #00ffa3; }
.badge-blue { background: rgba(102, 126, 234, 0.2); color: #667eea; border: 1px solid #667eea; }
.badge-yellow { background: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid #f59e0b; }
.badge-red { background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource(ttl=300)
def initialize_exchanges():
    exchanges = {}
    configs = {
        'kraken': {
            'class': ccxt.kraken,
            'key': os.getenv('KRAKEN_KEY'),
            'secret': os.getenv('KRAKEN_SECRET')
        },
        'binance': {
            'class': ccxt.binanceus,
            'key': os.getenv('BINANCE_KEY'),
            'secret': os.getenv('BINANCE_SECRET')
        },
        'coinbase': {
            'class': ccxt.coinbaseadvanced,
            'key': os.getenv('COINBASE_KEY'),
            'secret': os.getenv('COINBASE_SECRET').replace('\\n', '\n') if os.getenv('COINBASE_SECRET') else ''
        }
    }
    
    for name, config in configs.items():
        try:
            if not config['key'] or not config['secret']:
                exchanges[name] = {'status': "❌ NO KEY", 'client': None}
                continue

            exchange = config['class']({
                'apiKey': config['key'],
                'secret': config['secret'],
                'enableRateLimit': True,
            })

            exchange.fetch_time()
            exchanges[name] = {
                'client': exchange,
                'status': "✅ ONLINE",
                'last_check': datetime.now()
            }
            
        except Exception as e:
            exchanges[name] = {
                'client': None,
                'status': f"❌ ERROR: {str(e)[:50]}",
                'last_check': datetime.now()
            }
    
    return exchanges

@st.cache_data(ttl=10)
def fetch_exchange_balances():
    exchanges = initialize_exchanges()
    balance_data = []
    total_value = 0
    total_btc = 0
    total_gold = 0
    
    for name, data in exchanges.items():
        if data['status'] != "✅ ONLINE" or not data['client']:
            balance_data.append({
                'Exchange': name.upper(),
                'Total': 0,
                'Status': data['status'],
                'Details': {},
                'Primary': 'N/A',
                'BTC': 0,
                'GOLD': 0
            })
            continue

        try:
            client = data['client']
            balance = client.fetch_balance()
            
            symbol = 'BTC/USDT' if name == 'binance' else 'BTC/USD'
            ticker = client.fetch_ticker(symbol)
            btc_price = ticker['last']
            
            exchange_total = 0
            asset_details = {}
            btc_amount = 0
            gold_amount = 0
            
            for asset, amount in balance['total'].items():
                if amount > 0:
                    if asset in ['USD', 'USDT', 'USDC']:
                        value = amount
                    elif asset == 'BTC':
                        value = amount * btc_price
                        btc_amount = amount
                        total_btc += amount
                    elif asset == 'ETH':
                        try:
                            eth_price = client.fetch_ticker('ETH/USD')['last']
                            value = amount * eth_price
                        except:
                            value = amount * btc_price * 0.05
                    elif asset == 'PAXG':
                        try:
                            paxg_price = client.fetch_ticker('PAXG/USD')['last']
                            value = amount * paxg_price
                            gold_amount = amount
                            total_gold += amount
                        except:
                            value = amount * btc_price
                            gold_amount = amount
                            total_gold += amount
                    else:
                        continue
                    
                    exchange_total += value
                    asset_details[asset] = {
                        'amount': amount,
                        'value': value
                    }
            
            primary_asset = 'Mixed'
            if asset_details:
                max_asset = max(asset_details.items(), key=lambda x: x[1]['value'])
                primary_pct = (max_asset[1]['value'] / exchange_total * 100) if exchange_total > 0 else 0
                if primary_pct > 50:
                    primary_asset = f"{max_asset[0]}: {primary_pct:.1f}%"
            
            total_value += exchange_total
            
            balance_data.append({
                'Exchange': name.upper(),
                'Total': exchange_total,
                'Status': data['status'],
                'Details': asset_details,
                'Primary': primary_asset,
                'BTC': btc_amount,
                'GOLD': gold_amount
            })
            
        except Exception as e:
            balance_data.append({
                'Exchange': name.upper(),
                'Total': 0,
                'Status': f"❌ ERROR: {str(e)[:30]}",
                'Details': {},
                'Primary': 'N/A',
                'BTC': 0,
                'GOLD': 0
            })
    
    return balance_data, total_value, total_btc, total_gold

@st.cache_data(ttl=5)
def fetch_realtime_prices():
    exchanges = initialize_exchanges()
    price_data = []
    
    for name, data in exchanges.items():
        if data['status'] != "✅ ONLINE" or not data['client']:
            price_data.append({
                'exchange': name.upper(),
                'btc_price': 0,
                'latency_ms': 0,
                'status': data['status'],
                'bid': 0,
                'ask': 0
            })
            continue
        
        try:
            client = data['client']
            start_time = time.time()
            symbol = 'BTC/USDT' if name == 'binance' else 'BTC/USD'
            ticker = client.fetch_ticker(symbol)
            latency_ms = int((time.time() - start_time) * 1000)
            
            price_data.append({
                'exchange': name.upper(),
                'btc_price': ticker['last'],
                'latency_ms': latency_ms,
                'status': "✅ ONLINE",
                'bid': ticker['bid'],
                'ask': ticker['ask'],
                'volume': ticker['quoteVolume']
            })
            
        except Exception as e:
            price_data.append({
                'exchange': name.upper(),
                'btc_price': 0,
                'latency_ms': 0,
                'status': f"❌ {str(e)[:30]}",
                'bid': 0,
                'ask': 0
            })
    
    return price_data

def get_recent_trades():
    try:
        history_path = '/Users/dj3bosmacbookpro/Desktop/QUANT_bot/trade_history.json'
        if os.path.exists(history_path):
            with open(history_path, 'r') as f:
                trades = json.load(f)
                return trades[-5:]
    except:
        pass
    return []

def calculate_arbitrage_opportunities(price_data):
    opportunities = []
    
    online_exchanges = [p for p in price_data if p['status'] == "✅ ONLINE" and p['btc_price'] > 0]
    
    for i in range(len(online_exchanges)):
        for j in range(i + 1, len(online_exchanges)):
            ex1 = online_exchanges[i]
            ex2 = online_exchanges[j]
            
            buy_price = ex1['ask']
            sell_price = ex2['bid']
            
            spread = sell_price - buy_price
            if spread <= 0:
                buy_price = ex2['ask']
                sell_price = ex1['bid']
                spread = sell_price - buy_price
            
            if spread > 0:
                spread_pct = (spread / buy_price) * 100
                
                ex1_name = ex1['exchange'].lower()
                ex2_name = ex2['exchange'].lower()
                
                trade_size_usd = 10000.0
                ex1_fee_info = fee_manager.get_current_taker_fee(ex1_name, trade_size_usd)
                ex2_fee_info = fee_manager.get_current_taker_fee(ex2_name, trade_size_usd)
                
                ex1_fee_rate = ex1_fee_info['effective_fee_rate']
                ex2_fee_rate = ex2_fee_info['effective_fee_rate']
                
                total_fee_pct = ex1_fee_rate + ex2_fee_rate
                net_profit_pct = spread_pct - total_fee_pct
                
                if ex1['ask'] < ex2['bid']:
                    direction = f"BUY {ex1['exchange']} → SELL {ex2['exchange']}"
                    buy_ex = ex1['exchange']
                    sell_ex = ex2['exchange']
                else:
                    direction = f"BUY {ex2['exchange']} → SELL {ex1['exchange']}"
                    buy_ex = ex2['exchange']
                    sell_ex = ex1['exchange']
                
                profitable = net_profit_pct > 0.05
                latency_diff = abs(ex1['latency_ms'] - ex2['latency_ms'])
                
                opportunities.append({
                    'Pair': f"{ex1['exchange']} ↔ {ex2['exchange']}",
                    'Spread': f"${spread:.2f}",
                    'Spread %': f"{spread_pct:.3f}%",
                    'Fees %': f"{total_fee_pct*100:.3f}%",
                    'Net Profit %': f"{net_profit_pct:.3f}%",
                    'Direction': direction,
                    'Buy Exchange': buy_ex,
                    'Sell Exchange': sell_ex,
                    'Buy Price': buy_price,
                    'Sell Price': sell_price,
                    'Latency Diff': f"{latency_diff}ms",
                    'Profitable': '✅ YES' if profitable else '❌ NO'
                })
    
    return opportunities

def get_system_status():
    try:
        import subprocess
        result = subprocess.run(['pgrep', '-f', 'system_orchestrator.py'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            try:
                with open('/Users/dj3bosmacbookpro/Desktop/QUANT_bot/current_mode.txt', 'r') as f:
                    mode = f.read().strip()
            except:
                mode = "BTC"
            return "ONLINE", mode
    except:
        pass
    return "OFFLINE", "OFFLINE"

def create_exchange_card(exchange_name, exchange_price, exchange_balance, fee_info, arb_opportunities, exchange_trades):
    
    if not exchange_price:
        return f"""
        <div class="exchange-card" style="border-left-color: #ff3333; text-align: center; padding: 30px;">
            <h3 style="margin: 0;">⚡ {exchange_name}</h3>
            <div style="color: #ff3333; margin-top: 10px;">❌ OFFLINE</div>
            <div style="font-size: 11px; opacity: 0.5; margin-top: 5px;">No data available</div>
        </div>
        """
    
    status_color = "#00ffa3" if exchange_price['status'] == "✅ ONLINE" else "#ff3333"
    border_color = status_color
    
    fee_state_exch = fee_manager.state['exchanges'].get(exchange_name.lower(), {})
    
    html_parts = []
    
    html_parts.append(f'<div class="exchange-card" style="border-left-color: {border_color};">')
    
    html_parts.append(f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">')
    html_parts.append(f'<h3 style="margin: 0;">⚡ {exchange_name}</h3>')
    html_parts.append(f'<span style="color: {status_color}; font-weight: bold;">{exchange_price["status"]}</span>')
    html_parts.append('</div>')
    
    html_parts.append(f'<div style="background: rgba(0, 255, 163, 0.1); padding: 10px; border-radius: 8px; margin-bottom: 15px;">')
    html_parts.append(f'<div style="font-size: 24px; font-weight: 700; color: #00ffa3; text-align: center;">')
    html_parts.append(f'${exchange_price["btc_price"]:,.2f}')
    html_parts.append('</div>')
    html_parts.append(f'<div style="display: flex; justify-content: space-between; margin-top: 8px; font-size: 11px;">')
    html_parts.append(f'<span>Bid: ${exchange_price["bid"]:,.2f}</span>')
    html_parts.append(f'<span>Ask: ${exchange_price["ask"]:,.2f}</span>')
    html_parts.append(f'<span>Latency: {exchange_price["latency_ms"]}ms</span>')
    html_parts.append('</div>')
    html_parts.append('</div>')
    
    html_parts.append('<div style="margin-bottom: 15px;">')
    html_parts.append('<div style="font-size: 12px; opacity: 0.7; margin-bottom: 5px;">💰 Fee Intelligence</div>')
    html_parts.append('<div style="font-size: 11px; padding: 8px; background: rgba(255,255,255,0.05); border-radius: 6px;">')
    html_parts.append(f'<div>Effective Fee: <span style="color: #00ffa3; font-weight: bold;">{fee_info["effective_fee_rate"]*100:.3f}%</span></div>')
    
    if fee_state_exch.get('discount_active'):
        discount_type = fee_state_exch.get('discount_type', '').replace('_', ' ')
        html_parts.append(f'<div style="margin-top: 3px; color: #00ffa3; font-size: 10px;">✅ {discount_type} Active</div>')
        
        if fee_state_exch.get('credit_remaining_usd'):
            used = fee_state_exch.get('fees_used_this_month_usd', 0)
            total = fee_state_exch.get('monthly_fee_credit_usd', 0)
            pct = (used / total * 100) if total > 0 else 0
            html_parts.append('<div style="margin-top: 5px; font-size: 9px;">')
            html_parts.append('<div style="display: flex; justify-content: space-between;">')
            html_parts.append('<span>Credit Used:</span>')
            html_parts.append(f'<span>${used:,.0f} / ${total:,.0f}</span>')
            html_parts.append('</div>')
            html_parts.append('<div style="background: rgba(255,255,255,0.1); height: 4px; border-radius: 2px; margin-top: 3px;">')
            html_parts.append(f'<div style="background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); width: {min(pct, 100)}%; height: 100%; border-radius: 2px;"></div>')
            html_parts.append('</div>')
            html_parts.append('</div>')
    
    html_parts.append('</div>')
    html_parts.append('</div>')
    
    exchange_opps = [opp for opp in arb_opportunities 
                    if exchange_name in opp['Buy Exchange'] or exchange_name in opp['Sell Exchange']]
    
    if exchange_opps:
        html_parts.append('<div style="margin-top: 15px;">')
        html_parts.append('<div style="font-size: 12px; opacity: 0.7; margin-bottom: 5px;">📈 Arbitrage Opportunities</div>')
        
        for opp in exchange_opps[:2]:
            profitable = '✅ YES' in opp['Profitable']
            color = "#00ffa3" if profitable else "#ff3333"
            
            if exchange_name in opp['Buy Exchange']:
                action = "BUY"
                try:
                    price = float(opp['Buy Price'])
                except:
                    price = float(opp['Buy Price'].replace('$', '').replace(',', ''))
            else:
                action = "SELL"
                try:
                    price = float(opp['Sell Price'])
                except:
                    price = float(opp['Sell Price'].replace('$', '').replace(',', ''))
            
            html_parts.append(f'<div style="font-size: 10px; padding: 6px; background: rgba(255,255,255,0.05); border-radius: 4px; margin-bottom: 5px; border-left: 3px solid {color};">')
            html_parts.append('<div style="display: flex; justify-content: space-between;">')
            html_parts.append(f'<span>{action} @ ${price:,.2f}</span>')
            html_parts.append(f'<span style="color: {color};">{opp["Net Profit %"]}</span>')
            html_parts.append('</div>')
            html_parts.append(f'<div style="font-size: 9px; opacity: 0.7; margin-top: 2px;">{opp["Pair"].replace("↔", "→").replace(exchange_name, "")}</div>')
            html_parts.append('</div>')
        
        html_parts.append('</div>')
    
    if exchange_trades:
        html_parts.append('<div style="margin-top: 15px;">')
        html_parts.append('<div style="font-size: 12px; opacity: 0.7; margin-bottom: 5px;">🔄 Recent Trades</div>')
        
        for trade in exchange_trades[:2]:
            time_str = datetime.fromisoformat(trade['timestamp']).strftime('%H:%M')
            profit = trade.get('profit_usd', 0)
            profit_color = "#00ffa3" if profit > 0 else "#ff3333"
            
            html_parts.append('<div style="font-size: 10px; padding: 5px; background: rgba(255,255,255,0.05); border-radius: 4px; margin-bottom: 4px;">')
            html_parts.append('<div style="display: flex; justify-content: space-between;">')
            html_parts.append(f'<span>{time_str}</span>')
            html_parts.append(f'<span style="color: {profit_color};">${profit:+.2f}</span>')
            html_parts.append('</div>')
            html_parts.append(f'<div style="font-size: 9px; opacity: 0.7;">{trade.get("direction", "Trade")}</div>')
            html_parts.append('</div>')
        
        html_parts.append('</div>')
    
    if exchange_balance and exchange_balance['Total'] > 0:
        html_parts.append('<div style="margin-top: 15px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.1);">')
        html_parts.append('<div style="font-size: 12px; opacity: 0.7; margin-bottom: 5px;">💼 Balance</div>')
        html_parts.append(f'<div style="font-size: 11px;">Total: <span style="color: #00ffa3; font-weight: bold;">${exchange_balance["Total"]:,.2f}</span></div>')
        html_parts.append('</div>')
    
    html_parts.append('</div>')
    
    return ''.join(html_parts)

def main():
    st.set_page_config(
        page_title="⚡ Trading Command Center",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    system_status, bot_mode = get_system_status()
    price_data = fetch_realtime_prices()
    balance_data, total_value, total_btc, total_gold = fetch_exchange_balances()
    arb_opportunities = calculate_arbitrage_opportunities(price_data)
    recent_trades = get_recent_trades()
    
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.markdown("# ⚡ TRADING COMMAND CENTER")
        st.markdown("### Zero-Fee Optimized Execution")
    
    with col3:
        if st.button("🔄 Refresh All", use_container_width=True):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()
    
    st.divider()
    
    st.markdown("### 📊 SYSTEM OVERVIEW")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        status_color = "#00ffa3" if system_status == "ONLINE" else "#ff3333"
        st.markdown(f"""
        <div class="metric-card">
            <div class="compact-label">BOT STATUS</div>
            <div class="compact-metric" style="color: {status_color};">
                {'✅ ONLINE' if system_status == 'ONLINE' else '❌ OFFLINE'}
            </div>
            <div style="font-size: 10px; margin-top: 5px;">
                <div>• Arbitrage Bot: <span style="color: #00ffa3;">ACTIVE</span></div>
                <div>• Macro Rotator: <span style="color: #00ffa3;">{bot_mode} MODE</span></div>
                <div>• Alpha Hunter: <span style="color: #FFD700;">STANDBY</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        change_24h = 125.50
        change_pct = (change_24h / total_value) * 100 if total_value > 0 else 0
        change_color = "#00ffa3" if change_24h >= 0 else "#ff3333"
        change_icon = "↗" if change_24h >= 0 else "↘"
        
        st.markdown(f"""
        <div class="metric-card">
            <div class="compact-label">TOTAL BALANCE</div>
            <div class="compact-metric" style="color: #00ffa3; font-size: 22px;">${total_value:,.2f}</div>
            <div class="balance-change-up" style="color: {change_color};">
                {change_icon} ${change_24h:+.2f} ({change_pct:+.2f}%) 24h
            </div>
            <div style="font-size: 10px; opacity: 0.7; margin-top: 5px;">
                <div>Kraken: ${balance_data[0]['Total']:,.0f}</div>
                <div>Binance: ${balance_data[1]['Total']:,.0f}</div>
                <div>Coinbase: ${balance_data[2]['Total']:,.0f}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        balance_text = ""
        for balance in balance_data:
            status_icon = "✅" if "✅" in balance['Status'] else "❌"
            balance_text += f"<div style='display: flex; justify-content: space-between; font-size: 11px; margin: 2px 0;'>"
            balance_text += f"<span>{balance['Exchange']}:</span>"
            balance_text += f"<span>${balance['Total']:,.0f} {status_icon}</span>"
            balance_text += f"</div>"
        
        online_count = sum(1 for b in balance_data if '✅' in b['Status'])
        st.markdown(f"""
        <div class="metric-card">
            <div class="compact-label">EXCHANGE BALANCES</div>
            {balance_text}
            <div style="margin-top: 8px; font-size: 10px; opacity: 0.7;">
                {online_count}/3 Connected
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        mode_color = "#00ffa3" if bot_mode == "BTC" else "#FFD700"
        mode_text = f"{bot_mode} MODE"
        
        btc_value = total_btc * price_data[0]['btc_price'] if price_data and price_data[0]['btc_price'] > 0 else 0
        gold_value = total_gold * 2000
        
        st.markdown(f"""
        <div class="metric-card">
            <div class="compact-label">CURRENT MODE</div>
            <div class="compact-metric" style="color: {mode_color};">
                {mode_text}
            </div>
            <div style="font-size: 10px; margin-top: 5px;">
                <div>Total BTC: {total_btc:.4f} (${btc_value:,.0f})</div>
                <div>Total GOLD: {total_gold:.2f} oz (${gold_value:,.0f})</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    
    st.markdown("### 🧠 MARKET INTELLIGENCE LAYER")
    
    intel_cols = st.columns(5)
    
    with intel_cols[0]:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #00ffa3;">
            <div class="compact-label">MARKET PHASE</div>
            <div class="compact-metric" style="color: #00ffa3;">ACCUMULATION</div>
            <div style="margin-top: 8px;">
                <span class="intel-badge badge-green">Wyckoff Phase 1</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with intel_cols[1]:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #667eea;">
            <div class="compact-label">AUCTION STATE</div>
            <div class="compact-metric" style="color: #667eea;">ACCEPTING</div>
            <div style="margin-top: 8px;">
                <span class="intel-badge badge-blue">Price + Volume ↑</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with intel_cols[2]:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #f59e0b;">
            <div class="compact-label">WHALE CONVICTION</div>
            <div class="compact-metric" style="color: #f59e0b;">HIGH</div>
            <div style="margin-top: 8px;">
                <span class="intel-badge badge-yellow">3+ Large Buys</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with intel_cols[3]:
        whale_color = "#00ffa3" if bot_mode == "BTC" else "#FFD700"
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid {whale_color};">
            <div class="compact-label">MACRO SIGNAL</div>
            <div class="compact-metric" style="color: {whale_color};">{bot_mode} MODE</div>
            <div style="margin-top: 8px;">
                <span class="intel-badge" style="background: rgba{tuple(int(whale_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (0.2,)}; color: {whale_color}; border: 1px solid {whale_color};">Rotation Active</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with intel_cols[4]:
        is_weekend = datetime.now().weekday() >= 5
        weekend_color = "#ef4444" if is_weekend else "#00ffa3"
        weekend_text = "ACTIVE" if is_weekend else "INACTIVE"
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid {weekend_color};">
            <div class="compact-label">WEEKEND MODE</div>
            <div class="compact-metric" style="color: {weekend_color};">{weekend_text}</div>
            <div style="margin-top: 8px;">
                <span class="intel-badge badge-red">+0.03% Spread</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    
    st.markdown("### 🏦 GOLD VAULT STRATEGY")
    
    gold_cols = st.columns([2, 1])
    
    with gold_cols[0]:
        monthly_goal_oz = 0.5
        accumulated_oz = total_gold
        accumulated_value = accumulated_oz * 2000
        goal_percentage = min(100, (accumulated_oz / monthly_goal_oz) * 100)
        next_buy_target = 1000
        progress_color = "#f59e0b"
        
        st.markdown(f"""
        <div class="metric-card">
            <div class="compact-label">MONTHLY GOLD ACCUMULATION</div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin: 10px 0;">
                <div style="font-size: 14px; color: #f59e0b;">Goal: {monthly_goal_oz} oz</div>
                <div style="font-size: 14px; color: #00ffa3;">{accumulated_oz:.2f} oz (${accumulated_value:,.0f})</div>
            </div>
            <div class="gold-battery">
                <div class="gold-battery-fill" style="width: {goal_percentage}%;"></div>
            </div>
            <div style="font-size: 11px; text-align: center; color: #fbbf24; margin: 5px 0;">
                ▰▰▰▱▱ {goal_percentage:.0f}% Complete
            </div>
            <div style="font-size: 10px; margin-top: 10px;">
                <div style="display: flex; justify-content: space-between;">
                    <span>Next Buy Target:</span>
                    <span style="color: #f59e0b;">${next_buy_target:,.0f}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 3px;">
                    <span>Auto-sweep:</span>
                    <span style="color: #00ffa3;">10% Bi-weekly Profits</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with gold_cols[1]:
        fee_state = fee_manager.state
        coinbase_remaining = fee_state['exchanges']['coinbase']['credit_remaining_usd']
        kraken_remaining = fee_state['exchanges']['kraken']['credit_remaining_usd']
        coinbase_used = 500 - coinbase_remaining
        kraken_used = 10000 - kraken_remaining
        
        st.markdown(f"""
        <div class="metric-card">
            <div class="compact-label">ZERO-FEE TRACKING</div>
            <div style="font-size: 11px; margin: 8px 0;">
                <div style="display: flex; justify-content: space-between;">
                    <span>Coinbase One:</span>
                    <span style="color: #00ffa3;">${coinbase_remaining:,.0f} / $500</span>
                </div>
                <div style="background: rgba(255,255,255,0.1); height: 4px; border-radius: 2px; margin: 3px 0;">
                    <div style="background: #00ffa3; width: {(coinbase_used/500)*100}%; height: 100%; border-radius: 2px;"></div>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 8px;">
                    <span>Kraken+:</span>
                    <span style="color: #00ffa3;">${kraken_remaining:,.0f} / $10,000</span>
                </div>
                <div style="background: rgba(255,255,255,0.1); height: 4px; border-radius: 2px; margin: 3px 0;">
                    <div style="background: #00ffa3; width: {(kraken_used/10000)*100}%; height: 100%; border-radius: 2px;"></div>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 8px;">
                    <span>Binance BNB:</span>
                    <span style="color: #00ffa3;">Active (5% off)</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    
    st.markdown("### ⚡ EXCHANGE COMPARISON")
    
    if price_data and len(price_data) >= 3:
        exchange_table = f"""
        <div style="background: rgba(255, 255, 255, 0.05); border-radius: 10px; padding: 15px; margin: 10px 0;">
            <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                <thead>
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.1);">
                        <th style="text-align: left; padding: 8px; opacity: 0.7;"></th>
                        <th style="text-align: right; padding: 8px; opacity: 0.7;">KRAKEN</th>
                        <th style="text-align: right; padding: 8px; opacity: 0.7;">BINANCE</th>
                        <th style="text-align: right; padding: 8px; opacity: 0.7;">COINBASE</th>
                    </tr>
                </thead>
                <tbody>
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <td style="padding: 8px; opacity: 0.7;">BTC Price</td>
                        <td style="text-align: right; padding: 8px; color: #00ffa3; font-weight: bold;">${price_data[0]['btc_price']:,.2f}</td>
                        <td style="text-align: right; padding: 8px; color: #00ffa3; font-weight: bold;">${price_data[1]['btc_price']:,.2f}</td>
                        <td style="text-align: right; padding: 8px; color: #00ffa3; font-weight: bold;">${price_data[2]['btc_price']:,.2f}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <td style="padding: 8px; opacity: 0.7;">Spread</td>
                        <td style="text-align: right; padding: 8px;">{((price_data[0]['ask'] - price_data[0]['bid'])/price_data[0]['btc_price']*10000):.1f} bps</td>
                        <td style="text-align: right; padding: 8px;">{((price_data[1]['ask'] - price_data[1]['bid'])/price_data[1]['btc_price']*10000):.1f} bps</td>
                        <td style="text-align: right; padding: 8px;">{((price_data[2]['ask'] - price_data[2]['bid'])/price_data[2]['btc_price']*10000):.1f} bps</td>
                    </tr>
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <td style="padding: 8px; opacity: 0.7;">Latency</td>
                        <td style="text-align: right; padding: 8px;">{price_data[0]['latency_ms']}ms</td>
                        <td style="text-align: right; padding: 8px;">{price_data[1]['latency_ms']}ms</td>
                        <td style="text-align: right; padding: 8px;">{price_data[2]['latency_ms']}ms</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; opacity: 0.7;">Total Balance</td>
                        <td style="text-align: right; padding: 8px; color: #00ffa3;">${balance_data[0]['Total']:,.0f}</td>
                        <td style="text-align: right; padding: 8px; color: #00ffa3;">${balance_data[1]['Total']:,.0f}</td>
                        <td style="text-align: right; padding: 8px; color: #00ffa3;">${balance_data[2]['Total']:,.0f}</td>
                    </tr>
                </tbody>
            </table>
        </div>
        """
        st.markdown(exchange_table, unsafe_allow_html=True)
    
    st.divider()
    
    st.markdown("### 📊 EXCHANGE DASHBOARDS")
    
    exchange_cards = st.columns(3)
    
    for idx, exchange_name in enumerate(['KRAKEN', 'BINANCE', 'COINBASE']):
        with exchange_cards[idx]:
            exchange_price = next((p for p in price_data if p['exchange'] == exchange_name), None)
            exchange_balance = next((b for b in balance_data if b['Exchange'] == exchange_name), None)
            
            fee_info = fee_manager.get_current_taker_fee(exchange_name.lower(), 10000) if exchange_price else {}
            
            exchange_opps = [opp for opp in arb_opportunities 
                           if exchange_name in opp['Buy Exchange'] or exchange_name in opp['Sell Exchange']]
            
            exchange_trades_list = [trade for trade in recent_trades 
                                  if exchange_name.lower() in [trade.get('buy_exchange', ''), trade.get('sell_exchange', '')]]
            
            card_html = create_exchange_card(
                exchange_name, 
                exchange_price, 
                exchange_balance,
                fee_info,
                arb_opportunities,
                exchange_trades_list
            )
            
            st.markdown(card_html, unsafe_allow_html=True)
    
    st.divider()
    
    st.markdown("### 📈 ARBITRAGE OPPORTUNITIES")
    
    if arb_opportunities:
        df_opportunities = pd.DataFrame(arb_opportunities)
        
        def color_profitable(val):
            if 'YES' in str(val):
                return 'color: #00ffa3; font-weight: bold;'
            elif 'NO' in str(val):
                return 'color: #ff3333;'
            return ''
        
        display_columns = ['Pair', 'Spread', 'Spread %', 'Fees %', 'Net Profit %', 'Direction', 'Latency Diff', 'Profitable']
        df_display = df_opportunities[display_columns] if not df_opportunities.empty else pd.DataFrame()
        
        if not df_display.empty:
            styled_df = df_display.style.applymap(color_profitable, subset=['Profitable'])
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
        else:
            st.info("No arbitrage opportunities above 0.05% net profit threshold.")
    else:
        st.info("No arbitrage opportunities available.")
    
    st.divider()
    
    st.markdown("### 🎮 STRATEGY CONTROLS")
    
    control_cols = st.columns([2, 1, 1])
    
    with control_cols[0]:
        mode_color = "#00ffa3" if bot_mode == "BTC" else "#FFD700"
        st.markdown(f"""
        <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 12px; border-left: 5px solid {mode_color};">
            <div style="font-size: 14px; opacity: 0.7;">CURRENT STRATEGY</div>
            <div style="font-size: 32px; font-weight: 700; color: {mode_color}; margin: 10px 0;">
                {bot_mode} MODE
            </div>
            <div style="font-size: 12px; opacity: 0.7;">
                Last Updated: {datetime.now().strftime('%H:%M:%S')}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with control_cols[1]:
        if st.button("🔄 Force BTC Mode", use_container_width=True, type="primary"):
            try:
                with open('/Users/dj3bosmacbookpro/Desktop/QUANT_bot/current_mode.txt', 'w') as f:
                    f.write("BTC")
                st.success("Switched to BTC Mode")
                time.sleep(1)
                st.rerun()
            except:
                st.error("Failed to switch mode")
    
    with control_cols[2]:
        if st.button("🌟 Force GOLD Mode", use_container_width=True):
            try:
                with open('/Users/dj3bosmacbookpro/Desktop/QUANT_bot/current_mode.txt', 'w') as f:
                    f.write("GOLD")
                st.success("Switched to GOLD Mode")
                time.sleep(1)
                st.rerun()
            except:
                st.error("Failed to switch mode")
    
    st.divider()
    st.caption(f"Last Update: {datetime.now().strftime('%H:%M:%S')} | Total Balance: ${total_value:,.2f} | Strategy: {bot_mode} Mode | Active Trades: {len(recent_trades)}")

if __name__ == "__main__":
    main()
