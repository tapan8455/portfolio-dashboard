from flask import Flask, render_template, request, jsonify, redirect, url_for
import yfinance as yf
import json
import threading
import os
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app)

ASSETS_FILE = 'assets.json'

# Load portfolio from assets.json if it exists, otherwise use an empty list.
def load_assets():
    if os.path.exists(ASSETS_FILE):
        with open(ASSETS_FILE, 'r') as f:
            try:
                return json.load(f)
            except Exception as e:
                print(f"Error loading assets: {e}")
                return []
    return []

# Save the portfolio to assets.json.
def save_assets(portfolio):
    with open(ASSETS_FILE, 'w') as f:
        json.dump(portfolio, f)

# Load existing portfolio on startup.
portfolio = load_assets()

def get_asset_info(symbol, currency='USD'):
    try:
        asset = yf.Ticker(symbol)
        history = asset.history(period='1d')
        if history.empty:
            return None
        price = history['Close'].iloc[-1]
        return {
            'symbol': symbol.upper(),
            'current_price': round(price, 2),
            'currency': currency.upper()
        }
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

def update_portfolio_prices():
    while True:
        updated = False
        for asset in portfolio:
            info = get_asset_info(asset['symbol'], asset['currency'])
            if info:
                asset['current_price'] = info['current_price']
                asset['percentage'] = round(((asset['current_price'] - asset['avg_price']) / asset['avg_price']) * 100, 2)
                updated = True
        if updated:
            save_assets(portfolio)
            socketio.emit('update_prices', portfolio)
        socketio.sleep(10)  # Update every 10 seconds

threading.Thread(target=update_portfolio_prices, daemon=True).start()

@app.route('/')
def portfolio_dashboard():
    total_value = sum(a['current_price'] for a in portfolio) if portfolio else 0
    best_performer = max(portfolio, key=lambda x: x['percentage'], default=None)
    worst_performer = min(portfolio, key=lambda x: x['percentage'], default=None)
    return render_template(
        'index.html',
        portfolio=portfolio,
        total_value=round(total_value, 2),
        best_performer=best_performer,
        worst_performer=worst_performer
    )

@app.route('/add', methods=['GET', 'POST'])
def add_asset():
    if request.method == 'POST':
        symbol = request.form['symbol'].upper()
        avg_price = float(request.form['avg_price'])
        currency = request.form['currency'].upper()
        info = get_asset_info(symbol, currency)
        if info:
            info['avg_price'] = avg_price
            info['percentage'] = round(((info['current_price'] - avg_price) / avg_price) * 100, 2)
            portfolio.append(info)
            save_assets(portfolio)
            return redirect(url_for('portfolio_dashboard'))
        else:
            return render_template('add_asset.html', error="Invalid asset! Try again.")
    return render_template('add_asset.html')

@app.route('/edit_asset/<symbol>', methods=['GET', 'POST'])
def edit_asset(symbol):
    asset = next((a for a in portfolio if a['symbol'] == symbol.upper()), None)
    if not asset:
        return "Asset not found!", 404
    if request.method == 'POST':
        new_avg = float(request.form['avg_price'])
        asset['avg_price'] = new_avg
        asset['percentage'] = round(((asset['current_price'] - new_avg) / new_avg) * 100, 2)
        save_assets(portfolio)
        return redirect(url_for('portfolio_dashboard'))
    return render_template('edit_asset.html', asset=asset)

@app.route('/search_stock', methods=['GET'])
def search_stock():
    query = request.args.get('query', '')
    url = f"https://financialmodelingprep.com/api/v3/search?query={query}&limit=10&exchange=NASDAQ"
    # Optionally add your API key: url += "&apikey=YOUR_API_KEY"
    try:
        r = requests.get(url)
        data = r.json()
        suggestions = []
        for item in data:
            ticker = item.get("symbol", "").upper()
            name = item.get("name", "")
            suggestions.append({"ticker": ticker, "name": name})
        return jsonify(suggestions)
    except Exception as e:
        print(f"Search error: {e}")
        return jsonify([])

@app.route('/get_graph/<symbol>/<period>')
def get_graph(symbol, period):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period)
        if df.empty:
            return jsonify({'x': [], 'y': []})
        x_data = df.index.strftime('%Y-%m-%d').tolist()
        y_data = df['Close'].tolist()
        return jsonify({'x': x_data, 'y': y_data})
    except Exception as e:
        print(f'Graph error: {e}')
        return jsonify({'x': [], 'y': []})
    
@app.route('/delete_asset/<symbol>', methods=['POST'])
def delete_asset(symbol):
    global portfolio
    # Remove the asset whose symbol matches (case-insensitive)
    portfolio = [asset for asset in portfolio if asset['symbol'] != symbol.upper()]
    save_assets(portfolio)
    return redirect(url_for('portfolio_dashboard'))
    

if __name__ == '__main__':
    socketio.run(app, debug=True)
