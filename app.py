from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
import yfinance as yf
import threading
import os, requests
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, current_user, login_required, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your_email_password'

db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode='eventlet')
login_manager = LoginManager(app)
login_manager.login_view = 'login'
mail = Mail(app)

# ---------------- Models ---------------- #
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    alert_threshold = db.Column(db.Float, default=10.0)
    negative_threshold = db.Column(db.Float, default=-5.0)
    assets = db.relationship('Asset', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    avg_price = db.Column(db.Float, nullable=False)
    current_price = db.Column(db.Float, nullable=False)
    percentage = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='USD')
    alerted = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    green_threshold = db.Column(db.Float, default=None)
    red_threshold = db.Column(db.Float, default=None)

# ---------------- Login Loader ---------------- #
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ---------------- Background Updater ---------------- #
def get_asset_info(symbol, currency='USD'):
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period='1d')
        if history.empty:
            return None
        price = history['Close'].iloc[-1]
        return {
            'symbol': symbol.upper(),
            'current_price': round(price, 2),
            'currency': currency.upper()
        }
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

def update_portfolio_prices():
    with app.app_context():
        while True:
            users = User.query.all()
            for user in users:
                for asset in user.assets:
                    info = get_asset_info(asset.symbol, asset.currency)
                    if info:
                        asset.current_price = info['current_price']
                        asset.percentage = round(((asset.current_price - asset.avg_price) / asset.avg_price) * 100, 2)
            db.session.commit()
            time.sleep(60)

# ---------------- Routes ---------------- #
@app.route('/')
@login_required
def portfolio_dashboard():
    assets = Asset.query.filter_by(user_id=current_user.id).all()
    portfolio = [
    {
        'symbol': asset.symbol,
        'avg_price': float(asset.avg_price),
        'current_price': float(asset.current_price),
        'currency': asset.currency,
        'percentage': float(asset.percentage),
        'highlight': (
            'green' if asset.percentage >= current_user.alert_threshold else
            'red' if asset.percentage <= current_user.negative_threshold else
            ''
        )
    } for asset in assets
]
    return render_template('index.html', portfolio=portfolio)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user = User(
            username=request.form['username'],
            email=request.form['email']
        )
        user.set_password(request.form['password'])
        if User.query.filter((User.username == user.username) | (User.email == user.email)).first():
            flash("Username or email already exists.", "danger")
            return redirect(url_for('register'))
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. Please login.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            return redirect(url_for('portfolio_dashboard'))
        flash("Invalid credentials.", "danger")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current = request.form['current_password']
        new = request.form['new_password']
        confirm = request.form['confirm_password']
        if not current_user.check_password(current):
            flash("Current password incorrect.", "danger")
        elif new != confirm:
            flash("New passwords do not match.", "danger")
        else:
            current_user.set_password(new)
            db.session.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for('portfolio_dashboard'))
    return render_template('change_password.html')

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_asset():
    if request.method == 'POST':
        symbol = request.form['symbol'].upper()
        avg_price = float(request.form['avg_price'])
        currency = request.form['currency'].upper()
        if Asset.query.filter_by(symbol=symbol, user_id=current_user.id).first():
            flash("Asset already exists!", "warning")
            return redirect(url_for('add_asset'))
        info = get_asset_info(symbol, currency)
        if info:
            asset = Asset(
                symbol=symbol,
                avg_price=avg_price,
                current_price=info['current_price'],
                currency=currency,
                percentage=round(((info['current_price'] - avg_price) / avg_price) * 100, 2),
                user_id=current_user.id
            )
            db.session.add(asset)
            db.session.commit()
            return redirect(url_for('portfolio_dashboard'))
        flash("Invalid asset symbol.", "danger")
    return render_template('add_asset.html')

@app.route('/edit_asset/<symbol>', methods=['GET', 'POST'])
@login_required
def edit_asset(symbol):
    asset = Asset.query.filter_by(symbol=symbol.upper(), user_id=current_user.id).first()
    if not asset:
        return "Asset not found", 404
    if request.method == 'POST':
        asset.avg_price = float(request.form['avg_price'])
        asset.percentage = round(((asset.current_price - asset.avg_price) / asset.avg_price) * 100, 2)
        db.session.commit()
        return redirect(url_for('portfolio_dashboard'))
    return render_template('edit_asset.html', asset=asset)

@app.route('/delete_asset/<symbol>', methods=['POST'])
@login_required
def delete_asset(symbol):
    asset = Asset.query.filter_by(symbol=symbol.upper(), user_id=current_user.id).first()
    if asset:
        db.session.delete(asset)
        db.session.commit()
    return redirect(url_for('portfolio_dashboard'))

@app.route('/update_threshold', methods=['POST'])
@login_required
def update_threshold():
    try:
        current_user.alert_threshold = float(request.form['positive_threshold'])
        current_user.negative_threshold = float(request.form['negative_threshold'])
        db.session.commit()
        flash("Thresholds updated.", "success")
    except Exception as e:
        flash(f"Update failed: {e}", "danger")
    return redirect(url_for('portfolio_dashboard'))

@app.route('/get_graph/<symbol>/<period>')
def get_graph(symbol, period):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period)
        if df.empty:
            return jsonify({'x': [], 'y': []})
        return jsonify({
            'x': df.index.strftime('%Y-%m-%d').tolist(),
            'y': df['Close'].tolist()
        })
    except Exception as e:
        print(f"Graph error: {e}")
        return jsonify({'x': [], 'y': []})

@app.route('/search_stock')
def search_stock():
    query = request.args.get('query', '')
    url = f"https://financialmodelingprep.com/api/v3/search?query={query}&limit=10&exchange=NASDAQ"
    try:
        r = requests.get(url)
        return jsonify([
            {"ticker": item.get("symbol", "").upper(), "name": item.get("name", "")}
            for item in r.json()
        ])
    except Exception as e:
        print("Search error:", e)
        return jsonify([])

# ---------------- Run App ---------------- #
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        threading.Thread(target=update_portfolio_prices, daemon=True).start()
    socketio.run(app, debug=True)