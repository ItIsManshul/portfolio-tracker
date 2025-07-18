import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import urllib.parse
import feedparser
import re
import requests
import json
import os


if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = "overview"

if "view_ticker" not in st.session_state:
    st.session_state["view_ticker"] = None

@st.cache_data(show_spinner=False)
def get_stock_info(ticker):
    stock = yf.Ticker(ticker)
    return stock.info

@st.cache_data(show_spinner=False)
def get_stock_history(ticker, period="1mo"):
    stock = yf.Ticker(ticker)
    return stock.history(period=period)

# --- SESSION STATE SETUP ---
if "holdings" not in st.session_state:
    st.session_state["holdings"] = []

if "sidebar_uploaded" not in st.session_state:
    st.session_state["sidebar_uploaded"] = False

def go_back():
    st.session_state["view_ticker"] = None
    st.rerun()

firebaseConfig = {
    "apiKey": "AIzaSyAmqd996_cpNFySbS1gYzM73VLCVS4fi_M",
    "authDomain": "portfoliotracker-5abc6.firebaseapp.com",
    "projectId": "portfoliotracker-5abc6",
    "storageBucket": "portfoliotracker-5abc6.appspot.com",
    "messagingSenderId": "69023883489",
    "appId": "1:69023883489:web:4be45f2586650bcb15d7a0",
    "measurementId": "G-HBEJS064RC",
    "databaseURL": ""  # Firestore doesn't use this, so you can leave it blank
}


# Firebase REST API login/signup
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")  # Or set it directly as a string
FIREBASE_AUTH_URL = "https://identitytoolkit.googleapis.com/v1/accounts"

def firebase_login(email, password):
    url = f"{FIREBASE_AUTH_URL}:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    res = requests.post(url, json=payload)
    if res.status_code == 200:
        return res.json()  # contains idToken, email, etc.
    else:
        raise ValueError("Login failed")

def firebase_signup(email, password):
    url = f"{FIREBASE_AUTH_URL}:signUp?key={FIREBASE_API_KEY}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    res = requests.post(url, json=payload)
    if res.status_code == 200:
        return res.json()
    else:
        raise ValueError("Sign-up failed")


# --- SAVE / LOAD PORTFOLIO FIRESTORE ---
def save_portfolio_to_firebase(email, portfolio_data):
    doc_path = f"https://firestore.googleapis.com/v1/projects/portfoliotracker-5abc6/databases/(default)/documents/portfolios/{email.replace('.', '_')}"
    headers = {"Content-Type": "application/json"}
    data = {
        "fields": {
            "holdings": {
                "stringValue": json.dumps(portfolio_data)
            }
        }
    }
    requests.patch(doc_path, headers=headers, json=data)


def load_portfolio_from_firebase(email):
    doc_path = f"https://firestore.googleapis.com/v1/projects/portfoliotracker-5abc6/databases/(default)/documents/portfolios/{email.replace('.', '_')}"
    res = requests.get(doc_path)
    if res.status_code == 200:
        doc = res.json()
        if "fields" in doc and "holdings" in doc["fields"]:
            return json.loads(doc["fields"]["holdings"]["stringValue"])
    return []





if st.session_state.get("active_tab") == "settings":
    st.markdown("## ⚙️ Portfolio Settings")
    st.divider()

    if "user" in st.session_state:
        user_email = st.session_state["user"]["email"]

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📤 Save Portfolio", key="save_full"):
                save_portfolio_to_firebase(user_email, st.session_state["holdings"])
                st.success("✅ Portfolio saved!")

        with col2:
            if st.button("📥 Load Portfolio", key="load_full"):
                loaded = load_portfolio_from_firebase(user_email)
                if loaded:
                    st.session_state["holdings"] = loaded
                    st.success("✅ Portfolio loaded!")
                    st.rerun()
                else:
                    st.warning("⚠️ No saved portfolio found.")

        with col3:
            # --- CLEAR PORTFOLIO BUTTON ---
                if st.button("🗑️ Clear Portfolio"):
                    st.session_state["holdings"] = []
                    st.session_state["sidebar_uploaded"] = False
                    st.rerun()
    else:
        st.warning("🔒 Please log in to use these features.")

    st.markdown("### 📎 Upload Portfolio CSV")
    st.markdown("Upload CSV file with columns: Ticker, Quantity, Buy Price")
    uploaded_file = st.file_uploader("Upload CSV", type="csv", key="full_csv_upload")

    if uploaded_file and not st.session_state.get("top_uploaded", False):
        df = pd.read_csv(uploaded_file)
        required_columns = {"Ticker", "Quantity", "Buy Price"}

        if not required_columns.issubset(df.columns):
            st.error("❌ CSV must contain: Ticker, Quantity, Buy Price")
        else:
            new_holdings = []
            for _, row in df.iterrows():
                ticker = str(row["Ticker"]).upper().strip()
                quantity = float(row["Quantity"])
                buy_price = float(row["Buy Price"])

                try:
                    stock = yf.Ticker(ticker)
                    current_price = None
                    company_name = "N/A"

                    if stock.fast_info and "last_price" in stock.fast_info:
                        current_price = stock.fast_info["last_price"]

                    if current_price is None:
                        hist = stock.history(period="1d")
                        if not hist.empty:
                            current_price = hist["Close"].iloc[-1]

                    company_name = stock.info.get("shortName", "N/A")

                    if current_price is None:
                        st.warning(f"⚠️ Skipped {ticker}: no price found.")
                        continue

                    market_value = round(current_price * quantity, 2)
                    cost_basis = round(buy_price * quantity, 2)
                    gain_loss = round(market_value - cost_basis, 2)
                    percent_return = round((gain_loss / cost_basis) * 100, 2) if cost_basis else 0

                    new_holdings.append({
                        "Company": company_name,
                        "Ticker": ticker,
                        "Quantity": quantity,
                        "Buy Price": buy_price,
                        "Current Price": current_price,
                        "Market Value": market_value,
                        "Gain/Loss": gain_loss,
                        "% Return": percent_return
                    })
                except Exception:
                    st.warning(f"⚠️ Skipped {ticker} – error during processing.")

            st.session_state["holdings"].extend(new_holdings)
            st.session_state["top_uploaded"] = True
            st.success("✅ Portfolio imported!")
            st.rerun()

    st.divider()
    st.markdown("### 🔒 Account")

    if "user" in st.session_state:
        if st.button("🚪 Log Out", key="logout_full"):
            del st.session_state["user"]
            st.success("✅ Logged out.")
            st.rerun()

    # --- Back Button ---
    st.divider()
    if st.button("🔙 Back to Dashboard", use_container_width=True, key="back_btn"):
        st.session_state["active_tab"] = "overview"
        st.rerun()


# --- TOP RIGHT REFRESH AND SETTINGS BUTTONS ---
header_left, header_right = st.columns([10, 2])
with header_right:
    col1, col2 = st.columns([1, 1])

    with col1:
        if st.button("🔄", use_container_width=True, key="refresh_btn"):
            st.rerun()

    with col2:
        if st.button("⚙️", use_container_width=True, key="settings_btn"):
            st.session_state["active_tab"] = "settings"
            st.rerun()


# --- PAGE CONFIG ---
st.set_page_config(page_title="Portfolio Tracker", layout="wide")



if st.session_state["view_ticker"]:
    st.title("📘 Company Specifics")
else:
    st.title("Personal Portfolio Tracker")

if st.session_state["view_ticker"]:
    selected = next((h for h in st.session_state["holdings"] if h["Ticker"] == st.session_state["view_ticker"]), None)

    if selected:
        st.title(f"📘 {selected['Company']} ({selected['Ticker']}) – Details")

        st.markdown("### 💼 Your Holding")
        col1, col2, col3 = st.columns(3)
        col1.metric("Quantity Held", selected["Quantity"])
        col2.metric("Buy Price", f"${selected['Buy Price']:.2f}")
        col3.metric("Current Price", f"${selected['Current Price']:.2f}")

        col4, col5, col6 = st.columns(3)
        col4.metric("Market Value", f"${selected['Market Value']:.2f}")
        col5.metric("Gain/Loss", f"${selected['Gain/Loss']:.2f}")
        col6.metric("% Return", f"{selected['% Return']:+.2f}%")

        st.markdown("### 📊 Stock Fundamentals")
        info = get_stock_info(selected["Ticker"])
        hist = get_stock_history(selected["Ticker"], period="1mo")

        left, right = st.columns(2)
        with left:
            market_cap = info.get("marketCap")
            if market_cap is not None:
                st.markdown(f"**Market Cap**: ${market_cap:,.0f}")
            else:
                st.markdown("**Market Cap**: N/A")
            st.markdown(f"**PE Ratio (TTM)**: {info.get('trailingPE', 'N/A')}")
            st.markdown(f"**EPS (TTM)**: {info.get('trailingEps', 'N/A')}")
            st.markdown(f"**Dividend Yield**: {info.get('dividendYield', 0) * 100:.2f}%")
        with right:
            st.markdown(f"**52-Week High**: ${info.get('fiftyTwoWeekHigh', 'N/A')}")
            st.markdown(f"**52-Week Low**: ${info.get('fiftyTwoWeekLow', 'N/A')}")
            st.markdown(f"**Sector**: {info.get('sector', 'N/A')}")
            st.markdown(f"**Industry**: {info.get('industry', 'N/A')}")

            st.subheader("📉 Price History")

        time_range = st.selectbox(
            "Select timeframe:",
            ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"],
            index=2,
            key="history_range"
        )

        try:
            history = yf.Ticker(selected["Ticker"]).history(period=time_range)
            if not history.empty:
                fig = px.line(
                    history,
                    x=history.index,
                    y="Close",
                    title=f"{selected['Company']} Stock Price ({time_range})",
                    labels={"Close": "Closing Price", "Date": "Date"},
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No historical data available.")
        except Exception as e:
            st.error(f"Error loading chart: {e}")

        if st.button("🔙 Back to Home"):
            st.session_state["view_ticker"] = None
            st.rerun()

    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.title("📊 Portfolio Navigation")

    # --- Navigation Buttons ---
    st.markdown("### 📄 Navigation")
    if st.button("📄 Overview"):
        st.session_state["active_tab"] = "overview"
    if st.button("📊 Analytics"):
        st.session_state["active_tab"] = "analytics"
    if st.button("🏢 Company Specifics"):
        st.session_state["active_tab"] = "company"
    if st.button("💰 Dividends"):
        st.session_state["active_tab"] = "dividends"

    # --- LOGIN SYSTEM ---
    st.subheader("🔐 Log In or Sign Up")
    with st.expander("🔑 Login / Sign Up"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")

        col1, col2 = st.columns(2)
        with col1:
            login_clicked = st.button("Log In")
        with col2:
            signup_clicked = st.button("Sign Up")

        user = None
        if login_clicked:
            try:
                user = firebase_login(email, password)
                st.session_state["user"] = user
                st.sidebar.success("✅ Logged in!")
                st.rerun()
            except:
                st.sidebar.error("❌ Login failed")

        elif signup_clicked:
            try:
                user = firebase_signup(email, password)
                st.session_state["user"] = user
                st.sidebar.success("✅ Account created!")
            except Exception as e:
                st.sidebar.error("❌ Sign-up failed")
                st.sidebar.error(f"Details: {str(e)}")


    # --- PORTFOLIO FUNCTIONS (only when logged in) ---
    
    # --- SAVE / LOAD PORTFOLIO FIRESTORE ---
    def save_portfolio_to_firebase(email, portfolio_data):
        doc_path = f"https://firestore.googleapis.com/v1/projects/portfoliotracker-5abc6/databases/(default)/documents/portfolios/{email.replace('.', '_')}"
        headers = {"Content-Type": "application/json"}
        data = {
            "fields": {
                "holdings": {
                    "stringValue": json.dumps(portfolio_data)
                }
            }
        }
        requests.patch(doc_path, headers=headers, json=data)


    def load_portfolio_from_firebase(email):
        doc_path = f"https://firestore.googleapis.com/v1/projects/portfoliotracker-5abc6/databases/(default)/documents/portfolios/{email.replace('.', '_')}"
        res = requests.get(doc_path)
        if res.status_code == 200:
            doc = res.json()
            if "fields" in doc and "holdings" in doc["fields"]:
                return json.loads(doc["fields"]["holdings"]["stringValue"])
        return []

    if "user" in st.session_state:
        user_email = st.session_state["user"]["email"]

        st.markdown("---")
        if st.button("⬆️ Save Portfolio"):
            save_portfolio_to_firebase(user_email, st.session_state["holdings"])
            st.success("Portfolio saved!")

        if st.button("⬇️ Load Portfolio"):
            loaded = load_portfolio_from_firebase(user_email)
            if loaded:
                st.session_state["holdings"] = loaded
                st.success("Portfolio loaded!")
                st.rerun()
            else:
                st.warning("No portfolio found.")

        # --- Manual Input Form ---
st.markdown("---")
st.sidebar.markdown("Enter your stock holdings below:")

with st.sidebar.form("input_form"):
    ticker_input = st.text_input("Stock Ticker (e.g., AAPL)")
    quantity_input = st.number_input("Quantity Purchased", min_value=0.0, step=1.0, key="qty")
    buy_price_input = st.number_input("Buy Price (per share)", min_value=0.0, step=0.01, key="price")
    submitted = st.form_submit_button("Add Holding")

# Pull the values safely **after** submission
if submitted:
    ticker = ticker_input.upper().strip() if ticker_input else ""
    quantity = float(quantity_input)
    buy_price = float(buy_price_input)

    if not ticker:
        st.error("❗ Please enter a valid stock ticker.")
    elif quantity <= 0:
        st.error("❗ Quantity must be greater than 0.")
    elif buy_price <= 0:
        st.error("❗ Buy price must be greater than 0.")
    else:
        try:
            stock = yf.Ticker(ticker)
            current_price = None

            if stock.fast_info and "last_price" in stock.fast_info:
                current_price = stock.fast_info["last_price"]

            if current_price is None:
                hist = stock.history(period="1d")
                if not hist.empty:
                    current_price = hist["Close"].iloc[-1]

            company_name = stock.info.get("shortName", "N/A")

            if current_price is None:
                st.error(f"⚠️ Could not fetch data for {ticker}.")
            else:
                existing_index = next((i for i, h in enumerate(st.session_state["holdings"]) if h["Ticker"] == ticker), None)

                if existing_index is not None:
                    existing = st.session_state["holdings"][existing_index]
                    old_quantity = float(existing.get("Quantity", 0))
                    old_buy_price = float(existing.get("Buy Price", 0))

                    new_quantity = old_quantity + quantity
                    new_cost = (old_buy_price * old_quantity) + (buy_price * quantity)
                    new_avg_price = new_cost / new_quantity if new_quantity else 0

                    market_value = round(current_price * new_quantity, 2)
                    cost_basis = round(new_avg_price * new_quantity, 2)
                    gain_loss = round(market_value - cost_basis, 2)
                    percent_return = round((gain_loss / cost_basis) * 100, 2) if cost_basis else 0

                    st.session_state["holdings"][existing_index] = {
                        "Company": company_name,
                        "Ticker": ticker,
                        "Quantity": new_quantity,
                        "Buy Price": new_avg_price,
                        "Current Price": current_price,
                        "Market Value": market_value,
                        "Gain/Loss": gain_loss,
                        "% Return": percent_return
                    }
                    st.success(f"✅ {ticker} updated!")
                else:
                    market_value = round(current_price * quantity, 2)
                    cost_basis = round(buy_price * quantity, 2)
                    gain_loss = round(market_value - cost_basis, 2)
                    percent_return = round((gain_loss / cost_basis) * 100, 2) if cost_basis else 0

                    st.session_state["holdings"].append({
                        "Company": company_name,
                        "Ticker": ticker,
                        "Quantity": quantity,
                        "Buy Price": buy_price,
                        "Current Price": current_price,
                        "Market Value": market_value,
                        "Gain/Loss": gain_loss,
                        "% Return": percent_return
                    })
                    st.success(f"✅ {ticker} added to your portfolio!")
        except Exception as e:
            st.error(f"⚠️ Error fetching data for {ticker}.")

            
            pass


if st.session_state["active_tab"] == "overview":
    # --- Overview Tab Content ---
    main_col, news_col = st.columns([2, 1])

    with main_col:
        st.title("📈 Your Portfolio Overview")
        df = pd.DataFrame(st.session_state["holdings"])

        if not df.empty:
            df["Company Link"] = df["Ticker"].apply(lambda t: f"https://finance.yahoo.com/quote/{t}")
            display_df = df[[
                "Company Link", "Company", "Quantity", "Buy Price", "Current Price", "Market Value", "Gain/Loss", "% Return"
            ]]

            st.data_editor(
                display_df,
                column_config={
                    "Company Link": st.column_config.LinkColumn(
                        label="Yahoo Finance",
                        help="Click to open on Yahoo Finance",
                        validate=r"^https://finance\.yahoo\.com/quote/[A-Z]+$",
                        display_text=r"https://finance\.yahoo\.com/quote/([A-Z]+)"
                    )
                },
                hide_index=True,
                use_container_width=True
            )

            st.markdown("### ⚙️ Portfolio Actions")
            action = st.selectbox("Choose an action:", ("None", "Delete a stock", "Download portfolio as CSV"), key="portfolio_action")

            if action == "Delete a stock":
                tickers = [h["Ticker"] for h in st.session_state["holdings"]]
                colA, colB = st.columns([3, 1])
                with colA:
                    stock_to_delete = st.selectbox("Select a stock to delete:", tickers, key="delete_select")
                with colB:
                    if st.button("🗑️ Delete Selected"):
                        index_to_delete = next((i for i, h in enumerate(st.session_state["holdings"]) if h["Ticker"] == stock_to_delete), None)
                        if index_to_delete is not None:
                            st.session_state["holdings"].pop(index_to_delete)
                            st.success(f"✅ {stock_to_delete} removed.")
                            st.rerun()

            elif action == "Download portfolio as CSV":
                csv_data = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="📥 Download CSV",
                    data=csv_data,
                    file_name="portfolio.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            # --- Summary Metrics ---
            st.subheader("📊 Portfolio Summary")
            total_market_value = df["Market Value"].sum()
            total_cost_basis = df["Buy Price"].multiply(df["Quantity"]).sum()
            total_gain_loss = total_market_value - total_cost_basis
            overall_return_pct = (total_gain_loss / total_cost_basis) * 100 if total_cost_basis else 0

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Market Value", f"${total_market_value:,.2f}")
            col2.metric("Total Cost Basis", f"${total_cost_basis:,.2f}")
            col3.metric("Total Gain/Loss", f"${total_gain_loss:,.2f}", delta_color="normal")
            col4.metric("Overall Return (%)", f"{overall_return_pct:.2f}%", delta_color="inverse")

        else:
            st.info("No holdings added yet. Use the sidebar to add some.")

    with news_col:
        st.markdown("## 📰 Latest News")
        st.markdown("---")
        st.info("🛠️ News integration coming soon!")

elif st.session_state["active_tab"] == "analytics":
    st.title("📈 Your Analytics")
    df = pd.DataFrame(st.session_state["holdings"])

    if not df.empty:
        st.subheader("📉 % Return by Holding")
        chart_data = df[["Ticker", "% Return"]].sort_values(by="% Return", ascending=False)
        st.bar_chart(data=chart_data.set_index("Ticker"))

        st.subheader("🥧 Portfolio Allocation by Holding")
        pie_data = df[["Ticker", "Market Value"]].groupby("Ticker").sum()
        pie_data = pie_data[pie_data["Market Value"] > 0]
        st.plotly_chart(
            px.pie(
                pie_data,
                values="Market Value",
                names=pie_data.index,
                title="Portfolio Allocation (%)",
                hole=0.4
            ),
            use_container_width=True
        )
    else:
        st.info("No data available for analytics. Add holdings to view charts.")

elif st.session_state["active_tab"] == "company":
    st.header("📘 Company Specifics")

    tickers = [h["Ticker"] for h in st.session_state["holdings"]]
    if not tickers:
        st.info("No holdings available.")
        st.stop()

    selected_ticker = st.session_state.get("view_ticker", tickers[0])
    selected_ticker = st.selectbox("Select a stock to view details:", tickers, index=tickers.index(selected_ticker) if selected_ticker in tickers else 0)

    holding = next((h for h in st.session_state["holdings"] if h["Ticker"] == selected_ticker), None)

    if holding:
        st.subheader(f"{holding['Company']} ({holding['Ticker']})")

        col1, col2, col3 = st.columns(3)
        col1.metric("Quantity Held", holding["Quantity"])
        col2.metric("Buy Price", f"${holding['Buy Price']:.2f}")
        col3.metric("Current Price", f"${holding['Current Price']:.2f}")

        col4, col5, col6 = st.columns(3)
        col4.metric("Market Value", f"${holding['Market Value']:.2f}")
        col5.metric("Gain/Loss", f"${holding['Gain/Loss']:.2f}")
        col6.metric("% Return", f"{holding['% Return']:+.2f}%")

        st.markdown("### 📊 Stock Fundamentals")
        info = get_stock_info(holding["Ticker"])
        left, right = st.columns(2)
        with left:
            st.markdown(f"**Market Cap**: ${info.get('marketCap', 0):,}")
            st.markdown(f"**PE Ratio (TTM)**: {info.get('trailingPE', 'N/A')}")
            st.markdown(f"**EPS (TTM)**: {info.get('trailingEps', 'N/A')}")
            st.markdown(f"**Dividend Yield**: {info.get('dividendYield', 0) * 100:.2f}%")
        with right:
            st.markdown(f"**52W High**: ${info.get('fiftyTwoWeekHigh', 'N/A')}")
            st.markdown(f"**52W Low**: ${info.get('fiftyTwoWeekLow', 'N/A')}")
            st.markdown(f"**Sector**: {info.get('sector', 'N/A')}")
            st.markdown(f"**Industry**: {info.get('industry', 'N/A')}")

        st.markdown("### 📈 Price History")
        range_selected = st.selectbox("Select timeframe", ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"], index=2)
        try:
            history = get_stock_history(holding["Ticker"], period=range_selected)
            if not history.empty:
                fig = px.line(history, x=history.index, y="Close", title=f"{holding['Company']} ({range_selected})")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No history available.")
        except Exception as e:
            st.error(f"Error fetching price data: {e}")

        if st.button("🔙 Back to Overview"):
            st.session_state["view_ticker"] = None
            st.session_state["active_tab"] = "overview"
            st.rerun()

elif st.session_state["active_tab"] == "dividends":
    st.title("💰 Dividends")
    st.title("💰 Dividend Income Overview")
    df = pd.DataFrame(st.session_state["holdings"])

    if df.empty:
        st.info("No holdings available to calculate dividends.")
        st.stop()

    dividend_data = []

    for holding in st.session_state["holdings"]:
        ticker = holding["Ticker"]
        quantity = holding["Quantity"]

        try:
            stock_info = get_stock_info(ticker)
            dividend_yield = stock_info.get("dividendYield", 0)  # Already a decimal like 0.018
            dividend_rate = stock_info.get("dividendRate", 0)  # In $ per share annually

            annual_income = dividend_rate * quantity if dividend_rate else 0

            dividend_data.append({
                "Ticker": ticker,
                "Company": holding["Company"],
                "Quantity": quantity,
                "Dividend Yield (%)": round(dividend_yield * 100, 2) if dividend_yield else 0,
                "Dividend/Share ($)": round(dividend_rate, 2) if dividend_rate else 0,
                "Annual Income ($)": round(annual_income, 2)
            })

        except Exception:
            continue

    dividend_df = pd.DataFrame(dividend_data)

    if dividend_df.empty:
        st.warning("None of your holdings currently have dividend information.")
    else:
        st.dataframe(dividend_df, use_container_width=True)

        total_income = dividend_df["Annual Income ($)"].sum()
        avg_yield = dividend_df["Dividend Yield (%)"].mean()

        st.markdown("### 📈 Summary")
        col1, col2 = st.columns(2)
        col1.metric("Total Annual Dividend Income", f"${total_income:,.2f}")
        col2.metric("Average Dividend Yield", f"{avg_yield:.2f}%")

        st.markdown("### 🥧 Income Contribution by Ticker")
        pie_chart = px.pie(
            dividend_df,
            names="Ticker",
            values="Annual Income ($)",
            title="Dividend Income Distribution",
            hole=0.4
        )
        st.plotly_chart(pie_chart, use_container_width=True)
