import streamlit as st
import pandas as pd
import os
import plotly.express as px

st.set_page_config(page_title="Crypto Bot Dashboard", page_icon="📈", layout="centered")

st.title("📱 Moniteur Paper Trading")

CSV_FILE = "trades.csv"

if not os.path.exists(CSV_FILE):
    st.info("Aucune donnée enregistrée pour le moment. Le bot est en attente de signaux.")
else:
    df = pd.read_csv(CSV_FILE)
    
    # 1. Métriques globales
    derniere_balance = float(df["Balance"].iloc[-1]) if not df.empty else 1000.0
    pnl_total = derniere_balance - 1000.0
    nb_trades = len(df[df["Action"].isin(["TP", "SL"])])
    gains = len(df[df["Action"] == "TP"])
    win_rate = (gains / nb_trades * 100) if nb_trades > 0 else 0.0

    col1, col2 = st.columns(2)
    col1.metric("Solde Virtuel", f"{derniere_balance:.2f} $", f"{pnl_total:+.2f} $")
    col2.metric("Taux de Réussite", f"{win_rate:.1f} %", f"{nb_trades} trades")

    st.markdown("---")

    # 2. Graphique d'évolution
    st.subheader("Courbe de Performance")
    fig = px.line(df, x="Timestamp", y="Balance", title="Évolution du capital (USD)", markers=True)
    st.plotly_chart(fig, use_container_width=True)

    # 3. Tableau des transactions
    st.subheader("Historique des ordres")
    st.dataframe(df.sort_index(ascending=False), use_container_width=True)

st.button("🔄 Rafraîchir les données")
