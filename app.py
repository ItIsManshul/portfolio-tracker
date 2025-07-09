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
import pyrebase


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

firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()
db = firebase.database()  # Optional; for now we’ll use Firestore via REST


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

        # Portfolio-specific info
        st.markdown("### 💼 Your Holding")
        col1, col2, col3 = st.columns(3)
        col1.metric("Quantity Held", selected["Quantity"])
        col2.metric("Buy Price", f"${selected['Buy Price']:.2f}")
        col3.metric("Current Price", f"${selected['Current Price']:.2f}")

        col4, col5, col6 = st.columns(3)
        col4.metric("Market Value", f"${selected['Market Value']:.2f}")
        col5.metric("Gain/Loss", f"${selected['Gain/Loss']:.2f}")
        col6.metric("% Return", f"{selected['% Return']:+.2f}%")

        # Stock-specific info
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

        # Let user select the time range
        time_range = st.selectbox(
            "Select timeframe:",
            ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"],
            index=2,  # default to "6mo"
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



# --- SIDEBAR INPUT FORM ---

# --- LOGIN SYSTEM ---
st.sidebar.subheader("🔐 Log In or Sign Up")

with st.sidebar.expander("🔑 Login / Sign Up"):
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
            user = auth.sign_in_with_email_and_password(email, password)
            st.session_state["user"] = user
            st.sidebar.success("✅ Logged in!")
            st.rerun()
        except:
            st.sidebar.error("❌ Login failed")

    elif signup_clicked:
        try:
            user = auth.create_user_with_email_and_password(email, password)
            st.session_state["user"] = user
            st.sidebar.success("✅ Account created!")
        except Exception as e:
            st.sidebar.error("❌ Sign-up failed")
            st.sidebar.error(f"Details: {str(e)}")



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

    st.sidebar.markdown("---")
    if st.sidebar.button("⬆️ Save Portfolio"):
        save_portfolio_to_firebase(user_email, st.session_state["holdings"])
        st.sidebar.success("Portfolio saved!")

    if st.sidebar.button("⬇️ Load Portfolio"):
        loaded = load_portfolio_from_firebase(user_email)
        if loaded:
            st.session_state["holdings"] = loaded
            st.sidebar.success("Portfolio loaded!")
            st.rerun()
        else:
            st.sidebar.warning("No portfolio found.")


st.sidebar.title("📊 Portfolio Tracker")
st.sidebar.markdown("Enter your stock holdings below:")

with st.sidebar.form("input_form"):
    ticker = st.text_input("Stock Ticker (e.g., AAPL)")
    quantity = st.number_input("Quantity Purchased", min_value=0.0, step=1.0)
    buy_price = st.number_input("Buy Price (per share)", min_value=0.0, step=0.01)
    submitted = st.form_submit_button("Add Holding")

# --- CLEAR PORTFOLIO BUTTON ---
st.sidebar.markdown("---")
if st.sidebar.button("🗑️ Clear Portfolio"):
    st.session_state["holdings"] = []
    st.session_state["sidebar_uploaded"] = False
    st.rerun()

# --- SIDEBAR CSV UPLOAD ---
st.sidebar.markdown("### 📤 Upload Portfolio CSV")
sidebar_file = st.sidebar.file_uploader("Upload CSV (Ticker, Quantity, Buy Price)", type="csv", key="sidebar_uploader")

if sidebar_file is not None and not st.session_state["sidebar_uploaded"]:
    uploaded_df = pd.read_csv(sidebar_file)
    required_columns = {"Ticker", "Quantity", "Buy Price"}

    if not required_columns.issubset(uploaded_df.columns):
        st.sidebar.error("❌ CSV must have: Ticker, Quantity, Buy Price")
    else:
        new_holdings = []
        for _, row in uploaded_df.iterrows():
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
                    st.sidebar.warning(f"⚠️ Skipped {ticker}: no price found.")
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
                st.sidebar.warning(f"⚠️ Skipped {ticker} – error during processing.")

        st.session_state["holdings"].extend(new_holdings)
        st.session_state["sidebar_uploaded"] = True
        st.sidebar.success("✅ Portfolio imported!")
        st.rerun()

# --- HANDLE SINGLE ENTRY FROM SIDEBAR FORM ---
if submitted:
    ticker = ticker.upper().strip() if ticker else ""

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
            company_name = "N/A"

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

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["📄 Overview", "📊 Analytics", "Company Specifics"])


# === OVERVIEW TAB ===
with tab1:
  
  main_col, news_col = st.columns([2, 1])

  
  with main_col:
  # all your portfolio display logic here
  
    st.title("📈 Your Portfolio Overview")
    df = pd.DataFrame(st.session_state["holdings"])

    if not df.empty:
        # Build Yahoo Finance URL
        df["Company Link"] = df["Ticker"].apply(lambda t: f"https://finance.yahoo.com/quote/{t}")

        # Create a new dataframe just for display
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


        # Portfolio Actions
        st.markdown("### ⚙️ Portfolio Actions")
        action = st.selectbox(
            "Choose an action:",
            ("None", "Delete a stock", "Download portfolio as CSV"),
            key="portfolio_action"
        )

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

        # Summary
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

    
    


# === ANALYTICS TAB ===
with tab2:
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

# === TAB 3: COMPANY SPECS ===
with tab3:
    st.header("📘 Company Specifics")

    tickers = [h["Ticker"] for h in st.session_state["holdings"]]
    if not tickers:
        st.info("No holdings available.")
        st.stop()

    selected_ticker = st.session_state["view_ticker"]
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
            st.session_state["active_tab"] = "📄 Overview"
            st.rerun() 
