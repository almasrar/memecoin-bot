import urllib.request
import urllib.parse
import json
import time
import os
import csv
from datetime import datetime

# ==========================================
# CONFIGURATION MULTICHAÎNE & PAPER TRADING
# ==========================================
PAPER_BALANCE = 1000.0      # Capital virtuel en USD
TRADE_AMOUNT_USD = 50.0     # Montant par trade simulé
SCAN_INTERVAL_SEC = 60      # Scan toutes les 60 secondes
CSV_FILE = "multichain_trades.csv"

# BLOCKCHAINS AUTORISÉES (Les plus actives pour les memecoins)
ALLOWED_CHAINS = ["solana", "base", "bsc"]

# FILTRES ANTI-GLISSEMENT & SÉCURITÉ
MIN_LIQUIDITY_USD = 30000.0   # Rejeter les tokens avec < 30 000$ de liquidité
MIN_VOLUME_24H = 50000.0      # Rejeter les tokens avec < 50 000$ de volume

# Identifiants Telegram
TELEGRAM_TOKEN = "VOTRE_TOKEN_BOTFATHER_ICI"
TELEGRAM_CHAT_ID = "VOTRE_CHAT_ID_ICI"

# Suivi des positions en cours : { token_address: {...} }
active_positions = {}

# ==========================================
# NOTIFICATIONS TELEGRAM
# ==========================================
def send_telegram(message):
    if "VOTRE_TOKEN" in TELEGRAM_TOKEN or not TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception as e:
        print(f"⚠️ Erreur Telegram : {e}")

# ==========================================
# 1. SCANNER MULTICHAÎNE (DEXSCREENER)
# ==========================================
def scan_dexscreener_multichain():
    """Récupère les tokens tendances sur Solana, Base et BSC."""
    url = "https://api.dexscreener.com/token-boosts/top/v1"
    headers = {'User-Agent': 'Mozilla/5.0'}
    tokens_by_chain = []
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            for item in data:
                chain = item.get("chainId")
                if chain in ALLOWED_CHAINS:
                    tokens_by_chain.append(item.get("tokenAddress"))
                if len(tokens_by_chain) >= 20:
                    break
    except Exception as e:
        print(f"⚠️ Erreur scan tendances : {e}")

    if not tokens_by_chain:
        return []

    tokens_str = ",".join(tokens_by_chain[:15])
    pairs_url = f"https://api.dexscreener.com/latest/dex/tokens/{tokens_str}"
    
    try:
        req = urllib.request.Request(pairs_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode()).get("pairs", [])
    except Exception as e:
        print(f"⚠️ Erreur lecture détails paires : {e}")
        return []

# ==========================================
# 2. ANALYSTE & FILTRE ANTI-SLIPPAGE
# ==========================================
def analyze_memecoin(pair):
    chain_id = pair.get("chainId", "unknown").upper()
    base_token = pair.get("baseToken", {})
    name = base_token.get("name", "Unknown")
    symbol = base_token.get("symbol", "TOKEN")
    address = base_token.get("address", "")
    url = pair.get("url", "")

    price = float(pair.get("priceUsd", 0) or 0)
    liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
    volume_24h = float(pair.get("volume", {}).get("h24", 0) or 0)
    price_change_m5 = float(pair.get("priceChange", {}).get("m5", 0) or 0)

    # Filtre anti-slippage
    if liquidity < MIN_LIQUIDITY_USD or volume_24h < MIN_VOLUME_24H:
        return None

    # Détection de momentum (+3% à +15% sur 5m)
    if 3.0 <= price_change_m5 <= 15.0 and price > 0:
        return {
            "chain": chain_id,
            "symbol": symbol,
            "name": name,
            "address": address,
            "price": price,
            "liquidity": liquidity,
            "m5_change": price_change_m5,
            "url": url
        }

    return None

# ==========================================
# 3. SURVEILLANCE DES TRADES
# ==========================================
def monitor_positions():
    global PAPER_BALANCE
    to_close = []

    for addr, trade in active_positions.items():
        url = f"https://api.dexscreener.com/latest/dex/tokens/{addr}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                pairs = json.loads(resp.read().decode()).get("pairs", [])
                if not pairs:
                    continue
                curr_price = float(pairs[0].get("priceUsd", 0))
        except Exception:
            continue

        if curr_price <= 0:
            continue

        # Take-Profit : +15%
        if curr_price >= trade['tp']:
            profit = (curr_price - trade['entry']) * trade['qty']
            PAPER_BALANCE += (TRADE_AMOUNT_USD + profit)
            msg = (
                f"🎯 *TAKE-PROFIT TOUCHÉ !* [{trade['chain']}]\n"
                f"Token : *${trade['symbol']}*\n"
                f"Entrée : `{trade['entry']:.6f}$` ➔ Sortie : `{curr_price:.6f}$`\n"
                f"Gain : *+{profit:.2f} USD* (+15%)\n"
                f"Solde : `{PAPER_BALANCE:.2f} USD`\n"
                f"[Voir sur DexScreener]({trade['url']})"
            )
            print(f"\n{msg}")
            send_telegram(msg)
            to_close.append(addr)

        # Stop-Loss : -7%
        elif curr_price <= trade['sl']:
            loss = (curr_price - trade['entry']) * trade['qty']
            PAPER_BALANCE += (TRADE_AMOUNT_USD + loss)
            msg = (
                f"🛑 *STOP-LOSS TOUCHÉ* [{trade['chain']}]\n"
                f"Token : *${trade['symbol']}*\n"
                f"Entrée : `{trade['entry']:.6f}$` ➔ Sortie : `{curr_price:.6f}$`\n"
                f"Perte : *{loss:.2f} USD* (-7%)\n"
                f"Solde : `{PAPER_BALANCE:.2f} USD`"
            )
            print(f"\n{msg}")
            send_telegram(msg)
            to_close.append(addr)

    for addr in to_close:
        del active_positions[addr]

def open_memecoin_trade(candidate):
    global PAPER_BALANCE
    if PAPER_BALANCE < TRADE_AMOUNT_USD:
        print(f"⚠️ Solde virtuel insuffisant ({PAPER_BALANCE:.2f}$).")
        return

    price = candidate['price']
    qty = TRADE_AMOUNT_USD / price
    sl = price * 0.93   # -7%
    tp = price * 1.15   # +15%
    PAPER_BALANCE -= TRADE_AMOUNT_USD

    active_positions[candidate['address']] = {
        "chain": candidate['chain'],
        "symbol": candidate['symbol'],
        "entry": price,
        "qty": qty,
        "sl": sl,
        "tp": tp,
        "url": candidate['url']
    }

    msg = (
        f"⚡ *NOUVEAU SIGNAL [{candidate['chain']}]*\n"
        f"Token : *${candidate['symbol']}* ({candidate['name']})\n"
        f"Liquidité : `{candidate['liquidity']:,.0f}$`\n"
        f"Hausse 5m : `+{candidate['m5_change']:.1f}%`\n"
        f"Mise : `50.00 USD`\n"
        f"Prix : `{price:.6f}$`\n"
        f"🛡️ SL (-7%) : `{sl:.6f}$` | 🎯 TP (+15%) : `{tp:.6f}$`\n"
        f"[Graphique DexScreener]({candidate['url']})"
    )
    print(f"\n{msg}")
    send_telegram(msg)

# ==========================================
# BOUCLE PRINCIPALE
# ==========================================
def main():
    print("==========================================")
    print("🌐 Bot Multichaîne (Solana / Base / BSC)")
    print(f"Mise par trade : {TRADE_AMOUNT_USD}$ | Solde : {PAPER_BALANCE}$")
  
    print("==========================================")
    send_telegram("🌐 *Bot Multichaîne Actif.* Surveillance en cours : Solana, Base et BSC.")

    while True:
        monitor_positions()

        pairs = scan_dexscreener_multichain()
        for pair in pairs:
            base_addr = pair.get("baseToken", {}).get("address")
            if base_addr in active_positions:
                continue

            candidate = analyze_memecoin(pair)
            if candidate:
                open_memecoin_trade(candidate)
                break

        time.sleep(SCAN_INTERVAL_SEC)

if __name__ == "__main__":
    main()
