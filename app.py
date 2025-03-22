from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
import yfinance as yf
import threading
import os, requests
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, current_user, login_required, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message

# --------------------------
# App & Extensions Setup
# --------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
# For local development, using SQLite; adjust as needed.
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email settings (configure these with your email credentials)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'         # Replace with your email
app.config['MAIL_PASSWORD'] = 'your_email_password'            # Replace with your email password or app password

db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode='eventlet')
login_manager = LoginManager(app)
login_manager.login_view = 'login'
mail = Mail(app)

# --------------------------
# Models
# --------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    alert_threshold = db.Column(db.Float, default=10.0)  # Users can set their own threshold

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

# --------------------------
# User Loader for Flask-Login
# --------------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --------------------------
# Helper Functions
# --------------------------
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
        print(f"Error fetching data for {symbol}: {e}")
        return None

def send_email_alert(user, asset):
    try:
        msg = Message(
            subject=f"Alert: {asset.symbol} has reached your threshold!",
            sender=app.config['MAIL_USERNAME'],
            recipients=[user.email]
        )
        msg.body = (f"Hello {user.username},\n\n"
                    f"Your asset {asset.symbol} has increased by {asset.percentage}%.\n"
                    f"Current Price: ${asset.current_price} {asset.currency}\n"
                    f"Average Price: ${asset.avg_price}\n\n"
                    "Regards,\nYour Portfolio Dashboard")
        mail.send(msg)
        print(f"Email alert sent to {user.email} for {asset.symbol}")
    except Exception as e:
        print(f"Failed to send email alert for {asset.symbol}: {e}")

# --------------------------
# Background Price Updater
# --------------------------
def update_portfolio_prices():
    while True:
        users = User.query.all()
        for user in users:
            user_assets = Asset.query.filter_by(user_id=user.id).all()
            updated = False
            for asset in user_assets:
                info = get_asset_info(asset.symbol, asset.currency)
                if info:
                    asset.current_price = info['current_price']
                    asset.percentage = round(((asset.current_price - asset.avg_price) / asset.avg_price) * 100, 2)
                    # Check against the user's alert threshold
                    if asset.percentage >= user.alert_threshold and not asset.alerted:
                        send_email_alert(user, asset)
                        asset.alerted = True
                    if asset.percentage < user.alert_threshold:
                        asset.alerted = False
                    updated = True
            if updated:
                db.session.commit()
                # Emit update for each user’s portfolio (for simplicity, we broadcast all assets)
                all_assets = Asset.query.all()
                data = [ { 'symbol': a.symbol, 'current_price': a.current_price, 'avg_price': a.avg_price,
                           'percentage': a.percentage, 'currency': a.currency, 'user_id': a.user_id }
                         for a in all_assets ]
                socketio.emit('update_prices', data)
        socketio.sleep(10)  # Update every 10 seconds

threading.Thread(target=update_portfolio_prices, daemon=True).start()

# --------------------------
# Authentication Routes
# --------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Username or email already exists.")
            return redirect(url_for('register'))
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. Please log in.")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('portfolio_dashboard'))
        else:
            flash("Invalid credentials. Please try again.")
            return redirect(url_for('login'))
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
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        if not current_user.check_password(current_password):
            flash("Current password is incorrect.")
            return redirect(url_for('change_password'))
        if new_password != confirm_password:
            flash("New passwords do not match.")
            return redirect(url_for('change_password'))
        current_user.set_password(new_password)
        db.session.commit()
        flash("Password changed successfully.")
        return redirect(url_for('portfolio_dashboard'))
    return render_template('change_password.html')

# --------------------------
# Portfolio & Asset Routes
# --------------------------
@app.route('/')
@login_required
def portfolio_dashboard():
    assets = Asset.query.filter_by(user_id=current_user.id).all()
    total_value = sum(a.current_price for a in assets) if assets else 0
    best_performer = max(assets, key=lambda a: a.percentage, default=None)
    worst_performer = min(assets, key=lambda a: a.percentage, default=None)
    return render_template('index.html',
                           portfolio=assets,
                           total_value=round(total_value, 2),
                           best_performer=best_performer,
                           worst_performer=worst_performer)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_asset():
    if request.method == 'POST':
        symbol = request.form['symbol'].upper()
        avg_price = float(request.form['avg_price'])
        currency = request.form['currency'].upper()
        info = get_asset_info(symbol, currency)
        if info:
            asset = Asset(symbol=symbol,
                          avg_price=avg_price,
                          current_price=info['current_price'],
                          currency=currency,
                          percentage=round(((info['current_price'] - avg_price) / avg_price) * 100, 2),
                          user_id=current_user.id,
                          alerted=False)
            db.session.add(asset)
            db.session.commit()
            return redirect(url_for('portfolio_dashboard'))
        else:
            flash("Invalid asset! Try again.")
            return redirect(url_for('add_asset'))
    return render_template('add_asset.html')

@app.route('/edit_asset/<symbol>', methods=['GET', 'POST'])
@login_required
def edit_asset(symbol):
    asset = Asset.query.filter_by(symbol=symbol.upper(), user_id=current_user.id).first()
    if not asset:
        return "Asset not found!", 404
    if request.method == 'POST':
        new_avg = float(request.form['avg_price'])
        asset.avg_price = new_avg
        asset.percentage = round(((asset.current_price - new_avg) / new_avg) * 100, 2)
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

@app.route('/search_stock', methods=['GET'])
def search_stock():
    query = request.args.get('query', '')
    url = f"https://financialmodelingprep.com/api/v3/search?query={query}&limit=10&exchange=NASDAQ"
    # Optionally, add your API key: url += "&apikey=YOUR_API_KEY"
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

# --------------------------
# Launch the App
# --------------------------
if __name__ == '__main__':
    # Create tables if they don't exist
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)