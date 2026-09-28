import os
import json
import math
from flask import Flask, request, jsonify
from binance.client import Client
from binance.enums import *

app = Flask(__name__)

API_KEY = os.environ.get("BINANCE_API_KEY")
API_SECRET = os.environ.get("BINANCE_API_SECRET")

client = Client(API_KEY, API_SECRET)

def step_size_round(quantity, step_size):
    """Binance miktar hassasiyetine (Step Size) göre yuvarlama fonksiyonu"""
    precision = int(round(-math.log10(float(step_size))))
    return math.floor(quantity * (10 ** precision)) / (10 ** precision)

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = json.loads(request.data)
        symbol = data.get('symbol')  # Örn: SOLUSDT
        action = data.get('action')  # buy veya sell
        leverage = 20                # Sabit 20x Kaldıraç
        
        # 1. Kaldıraç Ayarla (20x)
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        
        # 2. Cüzdandaki Kullanılabilir Bakiyeyi Al ve 4'e Böl (%25 Kullan)
        account = client.futures_account()
        available_balance = float(account['availableBalance'])
        margin_to_use = available_balance / 4.0  # Parayı 4'e böldük
        
        # 3. Güncel Fiyatı ve Coin Hassasiyetini Al
        ticker = client.futures_symbol_ticker(symbol=symbol)
        entry_price = float(ticker['price'])
        
        symbol_info = client.futures_exchange_info()
        step_size = "1"
        for s in symbol_info['symbols']:
            if s['symbol'] == symbol:
                for f in s['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        step_size = f['stepSize']
                        break

        # 4. Pozisyon Büyüklüğünü Hesapla (Marjin * 20 / Fiyat)
        position_value_usdt = margin_to_use * leverage
        raw_quantity = position_value_usdt / entry_price
        quantity = step_size_round(raw_quantity, step_size)

        if quantity <= 0:
            return jsonify({"status": "error", "message": "Bakiye yetersiz"}), 400

        # 5. LONG (BUY) İŞLEMİ
        if action.lower() == 'buy':
            order = client.futures_create_order(
                symbol=symbol, side=SIDE_BUY, type=ORDER_TYPE_MARKET, quantity=quantity
            )
            
            # %1.5 Stop-Loss (Terse gidince %30 kayıp)
            stop_price = round(entry_price * 0.985, 2)
            # %1.0 Kâr Al (Doğru gidince %20 kâr)
            tp_price = round(entry_price * 1.010, 2)
            
            # Stop Loss Emri
            client.futures_create_order(
                symbol=symbol, side=SIDE_SELL, type=FUTURE_ORDER_TYPE_STOP_MARKET,
                stopPrice=stop_price, closePosition=True
            )
            # Take Profit Emri
            client.futures_create_order(
                symbol=symbol, side=SIDE_SELL, type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
                stopPrice=tp_price, closePosition=True
            )
            
        # 6. SHORT (SELL) İŞLEMİ
        elif action.lower() == 'sell':
            order = client.futures_create_order(
                symbol=symbol, side=SIDE_SELL, type=ORDER_TYPE_MARKET, quantity=quantity
            )
            
            # %1.5 Stop-Loss (Terse gidince %30 kayıp)
            stop_price = round(entry_price * 1.015, 2)
            # %1.0 Kâr Al (Doğru gidince %20 kâr)
            tp_price = round(entry_price * 0.990, 2)
            
            # Stop Loss Emri
            client.futures_create_order(
                symbol=symbol, side=SIDE_BUY, type=FUTURE_ORDER_TYPE_STOP_MARKET,
                stopPrice=stop_price, closePosition=True
            )
            # Take Profit Emri
            client.futures_create_order(
                symbol=symbol, side=SIDE_BUY, type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
                stopPrice=tp_price, closePosition=True
            )

        return jsonify({"status": "success", "message": f"{symbol} için bakiyenin 1/4'i ile işlem açıldı."}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
