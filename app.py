
import os
import hmac
import secrets
import sqlite3
from functools import wraps
from flask import (
    Flask, request, redirect, url_for,
    session, render_template_string, abort
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
DB_PATH = os.path.join(os.path.dirname(__file__), "orders.db")

# SAMPLE rates in INR per 1,000 units. Change these to your actual rates
# before accepting real orders; this panel does not deliver services automatically.
SERVICE_RATES = {
    "Telegram Post Views (Sample)": 10.00,
    "Telegram Channel Members (Sample)": 50.00,
    "Telegram Group Members (Sample)": 50.00,
}
MIN_QUANTITY = 1
MAX_QUANTITY = 1_000_000

if not all([app.secret_key, ADMIN_USERNAME, ADMIN_PASSWORD]):
    raise RuntimeError("Admin settings missing. Set them in PowerShell.")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False
)

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT NOT NULL,
                group_link TEXT NOT NULL,
                details TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(orders)").fetchall()}
        for name, definition in {
            "quantity": "INTEGER NOT NULL DEFAULT 1",
            "unit_price": "REAL NOT NULL DEFAULT 0",
            "total_price": "REAL NOT NULL DEFAULT 0",
            "payment_status": "TEXT NOT NULL DEFAULT 'Manual payment pending'",
        }.items():
            if name not in columns:
                db.execute(f"ALTER TABLE orders ADD COLUMN {name} {definition}")

init_db()

LOGIN_PAGE = """
<!doctype html><html><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin Login</title>
<style>
body{font-family:Arial;background:#100d19;color:white;padding:30px}
input{padding:10px;margin:8px 0;width:95%}
button{padding:11px;background:#7c3aed;color:white;border:0;border-radius:7px}
h2{color:#c084fc}
</style></head><body>
<h2>✦ Telegram SMM Panel</h2><h3>Admin Login</h3>
{% if error %}<p>{{ error }}</p>{% endif %}
<form method="post">
<input type="hidden" name="csrf_token" value="{{ csrf }}">
<p>Username</p><input name="username" required>
<p>Password</p><input type="password" name="password" required>
<p><button>Login</button></p></form></body></html>
"""

DASHBOARD = """
<!doctype html><html lang="en"><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Purple SMM Dashboard</title>
<style>
*{box-sizing:border-box}
body{margin:0;font-family:Arial;background:#100d19;color:#f5f0ff}
header{padding:22px;background:#1b142b;border-bottom:1px solid #49305f}
header h1{margin:0;color:#c084fc}
.layout{display:flex;min-height:80vh}
aside{width:210px;background:#191326;padding:20px}
aside a{display:block;padding:13px;color:#e9d5ff;text-decoration:none;border-radius:8px}
aside a:hover{background:#6d28d9}
main{flex:1;min-width:0;padding:24px}
.card{background:#211832;border:1px solid #49305f;padding:20px;border-radius:12px;margin-bottom:20px}
h2,h3{color:#c084fc}
input,select,textarea{width:100%;padding:11px;margin:7px 0 14px;border-radius:6px;border:1px solid #604477;background:#171020;color:white}
button{padding:11px 17px;border:0;border-radius:7px;background:#7c3aed;color:white;cursor:pointer}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:9px;border-bottom:1px solid #49305f;overflow-wrap:anywhere}
.small{color:#c4b5d9}
@media(max-width:650px){.layout{display:block}aside{width:100%}main{padding:12px}table{font-size:12px}}
</style></head><body>
<header><h1>✦ Telegram SMM Panel</h1><p class="small">Purple Edition</p></header>
<div class="layout"><aside>
<a href="/dashboard">⌂ Dashboard</a>
<a href="#new-order">✦ Telegram Services</a>
<a href="#orders">📋 Order History</a>
</aside><main>
<h2>Welcome, Admin! 💜</h2>
{% for message in messages %}<p>{{ message }}</p>{% endfor %}
<div class="card"><h3>Panel Overview</h3>
<p>Total Orders: {{ orders|length }}</p>
<p class="small">Orders are requests; automatic delivery is not enabled.</p></div>

<div class="card" id="new-order">
<h3>Submit Telegram Promotion Request</h3>
<form method="post" action="/create-order">
<input type="hidden" name="csrf_token" value="{{ csrf }}">
<p class="small">Sample INR rates per 1,000 units. Update SERVICE_RATES in app.py before taking real orders.</p>
<label>Service</label>
<select id="service" name="service" required>
<option value="">Choose a service</option>
{% for service, rate in rates.items() %}
<option value="{{ service }}">{{ service }} — ₹{{ '%.2f'|format(rate) }} per 1,000</option>
{% endfor %}
</select>
<label>Public Telegram group/channel link</label>
<input name="group_link" type="url" placeholder="https://t.me/yourgroup" required maxlength="300">
<label>Quantity</label>
<input id="quantity" name="quantity" type="number" min="1" max="1000000" step="1" value="1000" required>
<label>Campaign details</label>
<textarea name="details" rows="3" required maxlength="1000" placeholder="Describe the promotion request"></textarea>
<p class="small">Estimated total: ₹<strong id="total-price">0.00</strong>. Payment is manual; no online payment is connected.</p>
<button type="submit">Save Order</button>
</form>
<script>
const rates = {{ rates|tojson }};
const serviceInput = document.getElementById('service');
const quantityInput = document.getElementById('quantity');
function updateTotal() {
  const rate = Number(rates[serviceInput.value] || 0);
  const qty = Math.max(0, Number(quantityInput.value || 0));
  document.getElementById('total-price').textContent = (rate * qty / 1000).toFixed(2);
}
serviceInput.addEventListener('change', updateTotal);
quantityInput.addEventListener('input', updateTotal);
updateTotal();
</script></div>

<div class="card" id="orders"><h3>Order History</h3>
{% if orders %}
<div style="overflow-x:auto"><table><tr><th>ID</th><th>Service</th><th>Link</th><th>Quantity</th><th>Rate/1000</th><th>Total</th><th>Payment</th><th>Details</th><th>Status</th><th>Date</th></tr>
{% for order in orders %}
<tr><td>{{ order['id'] }}</td><td>{{ order['service'] }}</td>
<td>{{ order['group_link'] }}</td><td>{{ order['quantity'] }}</td>
<td>₹{{ '%.2f'|format(order['unit_price']) }}</td><td>₹{{ '%.2f'|format(order['total_price']) }}</td>
<td>{{ order['payment_status'] }}</td><td>{{ order['details'] }}</td>
<td>
<form method="post" action="/update-order/{{ order['id'] }}">
<input type="hidden" name="csrf_token" value="{{ csrf }}">
<select name="status" onchange="this.form.submit()">
<option value="Pending" {% if order['status'] == 'Pending' %}selected{% endif %}>Pending</option>
<option value="In Progress" {% if order['status'] == 'In Progress' %}selected{% endif %}>In Progress</option>
<option value="Completed" {% if order['status'] == 'Completed' %}selected{% endif %}>Completed</option>
<option value="Cancelled" {% if order['status'] == 'Cancelled' %}selected{% endif %}>Cancelled</option>
</select>
</form>
</td>
{% endfor %}</table></div>
{% else %}<p>No orders yet.</p>{% endif %}
</div>
<form method="post" action="/logout">
<input type="hidden" name="csrf_token" value="{{ csrf }}">
<button type="submit">Logout</button></form>
</main></div></body></html>
"""

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def check_csrf():
    token = request.form.get("csrf_token", "")
    saved = session.get("csrf_token", "")
    if not saved or not hmac.compare_digest(token, saved):
        abort(400)

@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("admin_logged_in"):
        return redirect(url_for("dashboard"))
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    error = ""
    if request.method == "POST":
        check_csrf()
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if (hmac.compare_digest(username, ADMIN_USERNAME)
                and hmac.compare_digest(password, ADMIN_PASSWORD)):
            session.clear()
            session["admin_logged_in"] = True
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("dashboard"))
        error = "Username ya password galat hai."
    return render_template_string(LOGIN_PAGE, error=error, csrf=session["csrf_token"])

@app.route("/dashboard")
@admin_required
def dashboard():
    with get_db() as db:
        orders = db.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    messages = session.pop("messages", [])
    return render_template_string(DASHBOARD, csrf=session["csrf_token"], orders=orders, messages=messages, rates=SERVICE_RATES)

@app.route("/create-order", methods=["POST"])
@admin_required
def create_order():
    check_csrf()
    service = request.form.get("service", "")
    group_link = request.form.get("group_link", "").strip()
    details = request.form.get("details", "").strip()
    try:
        quantity = int(request.form.get("quantity", ""))
    except (TypeError, ValueError):
        abort(400, "Quantity must be a whole number.")
    if service not in SERVICE_RATES:
        abort(400, "Please choose a valid service.")
    if not group_link.startswith(("https://t.me/", "http://t.me/")) or len(group_link) > 300:
        abort(400, "Please enter a valid Telegram link.")
    if not details or len(details) > 1000:
        abort(400, "Campaign details are required.")
    if quantity < MIN_QUANTITY or quantity > MAX_QUANTITY:
        abort(400, f"Quantity must be between {MIN_QUANTITY} and {MAX_QUANTITY}.")
    unit_price = float(SERVICE_RATES[service])
    total_price = round(unit_price * quantity / 1000, 2)
    with get_db() as db:
        db.execute(
            """INSERT INTO orders
               (service, group_link, details, quantity, unit_price, total_price, payment_status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (service, group_link, details, quantity, unit_price, total_price, "Manual payment pending")
        )
    session["messages"] = [f"Order saved. Estimated total: ₹{total_price:.2f}. Manual payment is pending."]
    return redirect(url_for("dashboard"))


@app.route("/logout", methods=["POST"])
@admin_required
def logout():
    check_csrf()
    session.clear()
    return redirect(url_for("login"))


@app.route("/update-order/<int:order_id>", methods=["POST"])
@admin_required
def update_order(order_id):
    check_csrf()
    status = request.form.get("status", "")
    allowed_statuses = {"Pending", "In Progress", "Completed", "Cancelled"}

    if status not in allowed_statuses:
        abort(400, "Invalid order status.")

    with get_db() as db:
        result = db.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id)
        )

        if result.rowcount == 0:
            abort(404, "Order not found.")

    session["messages"] = ["Order status updated successfully!"]
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
