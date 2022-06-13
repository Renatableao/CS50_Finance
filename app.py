import os
import re

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Query portfolio database for users stock symbols and store in variable
    symbol = db.execute("SELECT symbol FROM portfolio WHERE user_id = ? AND shares <> 0", session.get("user_id"))
    portfolio = []

    # For each symbol in list add to it information on how many shares user has and its total value
    for row in symbol:
        quote = lookup(row["symbol"])
        shares = db.execute("SELECT shares FROM portfolio WHERE symbol = ?", row["symbol"])
        quote["shares"] = shares[0]["shares"]
        quote["total"] = shares[0]["shares"] * quote["price"]
        portfolio.append(quote)

    # Get total amount of users stocks value
    total = sum([item['total'] for item in portfolio])

    # Get information of users cash balance
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session.get("user_id"))

    # Send all info to html page
    return render_template("index.html", portfolio=portfolio, cash=cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # User reached route via POST
    if request.method == "POST":

        # Ensure symbol is provided
        if not request.form.get("symbol"):
            return apology("Must provide symbol", 400)

        # Ensure shares are provided
        if not request.form.get("shares"):
            return apology("Must provide number of shares", 400)

        #  Ensure shares are given as intergers
        if not request.form.get("shares").isdigit():
            return apology("Must provide valid number of shares", 400)

        # Query API database for information on quotes
        quote = lookup(request.form.get("symbol"))

        # Ensure symbol is valid
        if quote:
            # Calculate cost of stock purchase and check users balance
            shares = request.form.get("shares")
            total = int(shares) * quote["price"]
            cash = db.execute("SELECT cash FROM users WHERE id = ?", session.get("user_id", None))

            # If user has enough cash
            if cash[0]["cash"] >= total:

                # Update users balance
                db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", total, session.get("user_id", None))

                # Insert transaction info into Transactions database
                db.execute("INSERT INTO transactions(user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
                           session.get("user_id", None), quote["symbol"], shares, quote["price"])

                # Update users Portfolio
                port_symbol = db.execute("SELECT symbol FROM portfolio WHERE user_id = ?", session.get("user_id", None))
                form_symbol = {"symbol": (request.form.get("symbol")).upper()}

                # If symbol already in users Portfolio
                if form_symbol in port_symbol:
                    db.execute("UPDATE portfolio SET shares = shares + ? WHERE symbol = ?",
                               request.form.get("shares"), (request.form.get("symbol")).upper())

                # If symbol not in users Portfolio
                else:
                    db.execute("INSERT INTO portfolio(user_id, symbol, shares) VALUES (?, ?, ?)",
                               session.get("user_id", None), quote["symbol"], shares)

                flash("Bought!")
                return redirect("/")

            # If user has not enough cash
            else:
                return apology("Not enough balance", 400)

        # If symbol not valid
        else:
            return apology("Symbol does not exist", 400)

    # User reached route via GET
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Get info from Transactions database
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = ?", session.get("user_id", None))

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST
    if request.method == "POST":

        # Ensure symbol is provided
        if not request.form.get("symbol"):
            return apology("Must provide symbol", 400)

        # Query API database for information on quotes
        quote = lookup(request.form.get("symbol"))

        # Ensure symbol is valid
        if quote:
            # Store information and send it to webpage
            name = quote["name"]
            symbol = quote["symbol"]
            price = quote["price"]

            return render_template("quote_result.html", name=name, symbol=symbol, price=price)

        # If symbol not valid
        else:
            return apology("Symbol does not exist", 400)

    # User reached route via GET
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("Must provide username", 400)

        # Ennsure username has at least 3 characters and not only numbers
        elif len(request.form.get("username")) < 3 or re.match('[0-9]', request.form.get("username")):
            return apology("Must provide valid username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("Must provide password", 400)

        # Ensure password has at least 6 characters and contain lowercase letters, numbers and special characters
        elif re.match('^(.{0,5}|[^0-9]*|[^a-z]*|[a-zA-Z0-9]*)$', request.form.get("password")):
            return apology("Must provide valid password", 400)

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("Must confirm password", 400)

        # Ensure password confirmation is the same as password
        elif request.form.get("confirmation") != request.form.get("password"):
            return apology("Passwords do not match", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username is not already used
        if len(rows) == 1:
            return apology("Username already in use", 400)

        hash = generate_password_hash(request.form.get("password"))

        db.execute("INSERT INTO users(username, hash) VALUES (?, ?)", request.form.get("username"), hash)

        # Remember which user has logged in
        user = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        session["user_id"] = user[0]["id"]

        # Redirect user to home page
        flash("Registered!")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

   # User reached route via POST
    if request.method == "POST":

        # Ensure symbol is provided
        if not request.form.get("symbol"):
            return apology("Must provide symbol", 400)

        # Ensure shares are provided
        if not request.form.get("shares"):
            return apology("Must provide number of shares", 400)

        # Query API database for information on quotes
        quote = lookup(request.form.get("symbol"))
        total = int(request.form.get("shares")) * quote["price"]

        # Check number of shares on users Porfolio for given symbol
        port_shares = db.execute("SELECT shares FROM portfolio WHERE user_id = ? AND symbol = ?",
                                 session.get("user_id"), (request.form.get("symbol")).upper())

        # If user has enough shares to sell
        if port_shares[0]["shares"] >= int(request.form.get("shares")):

            # Update users balance
            db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", total, session.get("user_id", None))

            # Insert transaction info into Transactions database
            db.execute("INSERT INTO transactions(user_id, symbol, shares, price) VALUES (?, ?, -?, ?)",
                       session.get("user_id", None), quote["symbol"], request.form.get("shares"), quote["price"])

            # Update Portfolio database
            db.execute("UPDATE portfolio SET shares = shares - ? WHERE symbol = ?",
                       request.form.get("shares"), (request.form.get("symbol")).upper())

            flash("Sold!")
            return redirect("/")

            # If user has not enough shares
        else:
            return apology("Not enough shares in portfolio", 400)

    # User reached route via GET
    else:
        # Select from users portifolio symbols with at least one share
        symbols = db.execute("SELECT symbol FROM portfolio WHERE user_id = ? AND shares <> 0", session.get("user_id"))
        return render_template("sell.html", symbols=symbols)
