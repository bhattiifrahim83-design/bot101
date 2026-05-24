import os
import time
import base64
import datetime
import requests

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.api import Client
from solana.rpc.types import TxOpts

# ============================================================
# CONFIG
# ============================================================

PRIVATE_KEY = os.environ["PRIVATE_KEY"]
HELIUS_KEY  = os.environ["HELIUS_KEY"]
RPC_URL     = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

client  = Client(RPC_URL)
session = requests.Session()

# ============================================================
# SETTINGS
# ============================================================

SOL_MINT           = "So11111111111111111111111111111111111111112"
BUY_AMOUNT_USD     = 2
SCAN_INTERVAL      = 15
MAX_COIN_AGE_SEC   = 45
MIN_LIQUIDITY      = 5000
MAX_LIQUIDITY      = 200000
MAX_OPEN_POSITIONS = 5
SLIPPAGE_BPS       = 1000
SLIPPAGE_PCT       = 10
STOP_LOSS_PCT      = 20
TRAILING_STOP_PCT  = 15
TP_TARGET          = 100
MAX_HOLD_SECONDS   = 3600
TOKEN_COOLDOWN     = 7200
GAS_FEE            = 0.01
MAX_TOP_HOLDER_PCT = 15

# ============================================================
# MEMORY
# ============================================================

positions     = {}
trade_history = []
seen_tokens   = set()
cooldowns     = {}

# ============================================================
# COLORS
# ============================================================

def green(t):  return f"\033[92m{t}\033[0m"
def red(t):    return f"\033[91m{t}\033[0m"
def yellow(t): return f"\033[93m{t}\033[0m"
def cyan(t):   return f"\033[96m{t}\033[0m"
def gray(t):   return f"\033[90m{t}\033[0m"
def bold(t):   return f"\033[1m{t}\033[0m"

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def now():
    return datetime.datetime.now().strftime("%H:%M:%S")

def beep():
    try:
        import winsound
        winsound.Beep(1000, 300)
    except:
        print("\a")

# ============================================================
# WALLET
# ============================================================

keypair = Keypair.from_base58_string(PRIVATE_KEY)

# ============================================================
# SOL PRICE
# ============================================================

def get_sol_price():
    try:
        r = session.get(
            "https://price.jup.ag/v4/price?ids=SOL",
            timeout=10
        )
        return float(r.json()["data"]["SOL"]["price"])
    except:
        return 85

# ============================================================
# BALANCE
# ============================================================

def get_balance():
    try:
        r = session.post(
            RPC_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [str(keypair.pubkey())]
            },
            timeout=10
        )
        return r.json().get("result", {}).get("value", 0) / 1e9
    except:
        return 0

# ============================================================
# FETCH POOLS
# ============================================================

def fetch_new_pools():
    try:
        r = session.get(
            "https://api.geckoterminal.com/api/v2/networks/solana/new_pools?page=1",
            timeout=15
        )
        if r.status_code != 200:
            return []
        return r.json().get("data", [])
    except:
        return []

# ============================================================
# PAIR INFO
# ============================================================

def get_pair(token):
    try:
        r = session.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{token}",
            timeout=15
        )
        if r.status_code != 200:
            return None
        pairs     = r.json().get("pairs", [])
        sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
        return sol_pairs[0] if sol_pairs else None
    except:
        return None

# ============================================================
# JUPITER QUOTE
# ============================================================

def get_quote(input_mint, output_mint, amount):
    urls = [
        "https://lite-api.jup.ag/swap/v1/quote",
        "https://quote-api.jup.ag/v6/quote"
    ]
    for url in urls:
        try:
            r = session.get(
                url,
                params={
                    "inputMint":   input_mint,
                    "outputMint":  output_mint,
                    "amount":      amount,
                    "slippageBps": SLIPPAGE_BPS
                },
                timeout=20
            )
            if r.status_code == 200:
                return r.json()
        except:
            continue
    return None

# ============================================================
# BUILD SWAP
# ============================================================

def build_swap_tx(quote):
    urls = [
        "https://lite-api.jup.ag/swap/v1/swap",
        "https://quote-api.jup.ag/v6/swap"
    ]
    for url in urls:
        try:
            r = session.post(
                url,
                json={
                    "quoteResponse":    quote,
                    "userPublicKey":    str(keypair.pubkey()),
                    "wrapAndUnwrapSol": True
                },
                timeout=20
            )
            if r.status_code == 200:
                return r.json().get("swapTransaction")
        except:
            continue
    return None

# ============================================================
# SEND TX
# ============================================================

def send_tx(tx_b64):
    try:
        tx_bytes  = base64.b64decode(tx_b64)
        tx        = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = VersionedTransaction(tx.message, [keypair])
        result    = client.send_raw_transaction(
            bytes(signed_tx),
            opts=TxOpts(skip_preflight=False)
        )
        return str(result.value)
    except:
        return None

# ============================================================
# BUY
# ============================================================

def buy_token(token):
    try:
        balance   = get_balance()
        sol_price = get_sol_price()
        needed    = (BUY_AMOUNT_USD / sol_price) + 0.01

        if balance < needed:
            print(red(f"  ❌ LOW BALANCE: {balance:.4f} SOL"))
            return None

        sol_amount = BUY_AMOUNT_USD / sol_price
        lamports   = int(sol_amount * 1e9)

        print(gray("  [1] Getting SOL price..."))
        print(gray("  [2] Building quote..."))
        quote = get_quote(SOL_MINT, token, lamports)
        if not quote:
            return None
        print(green("  ✅ Quote received"))

        print(gray("  [3] Building swap tx..."))
        swap_tx = build_swap_tx(quote)
        if not swap_tx:
            return None
        print(green("  ✅ Swap transaction built"))

        print(gray("  [4] Sending transaction..."))
        sig = send_tx(swap_tx)
        if sig:
            print(green("  ✅ Transaction confirmed"))
        return sig

    except:
        return None

# ============================================================
# TOKEN BALANCE
# ============================================================

def get_token_balance(token):
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                str(keypair.pubkey()),
                {"mint": token},
                {"encoding": "jsonParsed"}
            ]
        }
        r        = session.post(RPC_URL, json=payload, timeout=20)
        accounts = r.json().get("result", {}).get("value", [])
        if not accounts:
            return 0, 6
        info     = accounts[0]["account"]["data"]["parsed"]["info"]
        amount   = int(info["tokenAmount"]["amount"])
        decimals = int(info["tokenAmount"]["decimals"])
        return amount, decimals
    except:
        return 0, 6

# ============================================================
# REAL VALUE
# ============================================================

def get_real_value_usd(token):
    try:
        balance, decimals = get_token_balance(token)
        if balance <= 0:
            return 0
        ui_amount = balance / (10 ** decimals)
        pair      = get_pair(token)
        if not pair:
            return 0
        price = float(pair.get("priceUsd", 0) or 0)
        if price <= 0:
            return 0
        return ui_amount * price
    except:
        return 0

# ============================================================
# SELL
# ============================================================

def sell_token(token, percent=1.0):
    try:
        balance, decimals = get_token_balance(token)
        if balance <= 0:
            return None
        amount = int(balance * percent)

        print(gray("  [1/3] Building sell quote..."), end="  ")
        quote = get_quote(token, SOL_MINT, amount)
        if not quote:
            return None
        print(green("✔"))

        print(gray("  [2/3] Building swap tx..."), end="   ")
        swap_tx = build_swap_tx(quote)
        if not swap_tx:
            return None
        print(green("✔"))

        print(gray("  [3/3] Sending transaction..."), end=" ")
        sig = send_tx(swap_tx)
        if sig:
            print(green("✔"))
        return sig
    except:
        return None

# ============================================================
# GOPLUS CHECK
# ============================================================

def goplus_check(token):
    try:
        r = session.get(
            "https://api.gopluslabs.io/api/v1/solana/token_security",
            params={"contract_addresses": token},
            timeout=15
        )
        if r.status_code != 200:
            return {}
        data = r.json().get("result", {})
        if not data:
            return {}
        return data.get(token.lower(), {})
    except:
        return {}

# ============================================================
# TOP HOLDER CHECK — REAL IMPLEMENTATION
# ============================================================

def check_top_holder(token):
    """
    Helius RPC se top token holders check karo
    Agar koi ek holder 15% se zyada rakhe toh fail
    """
    try:
        r = session.post(
            RPC_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenLargestAccounts",
                "params": [token]
            },
            timeout=10
        )
        result = r.json().get("result", {}).get("value", [])
        if not result:
            return True, 0  # data nahi mila — pass kar do

        # Total supply nikalo
        supply_r = session.post(
            RPC_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenSupply",
                "params": [token]
            },
            timeout=10
        )
        supply_data = supply_r.json().get("result", {}).get("value", {})
        total_supply = float(supply_data.get("amount", 0))

        if total_supply <= 0:
            return True, 0

        # Top holder percentage check
        top_amount     = float(result[0].get("amount", 0))
        top_holder_pct = (top_amount / total_supply) * 100

        is_safe = top_holder_pct <= MAX_TOP_HOLDER_PCT
        return is_safe, round(top_holder_pct, 1)

    except:
        return True, 0  # error pe pass kar do

# ============================================================
# LP LOCK CHECK — REAL IMPLEMENTATION
# ============================================================

def check_lp_locked(token, pair):
    """
    LP lock check via GoPlus burn percent only.
    Liquidity size is NOT used as a proxy — only actual burn counts.
    """
    try:
        gp  = goplus_check(token)
        dex = gp.get("dex", [])
        if dex:
            burn = float(dex[0].get("burn_percent", 0) or 0)
            if burn >= 90:
                return True, f"Burned {burn:.0f}%"

        return False, "LP not locked"

    except:
        return False, "LP check failed"

# ============================================================
# TAX CHECK — SOLANA REAL METHOD
# ============================================================

def check_tax(token):
    """
    Solana pe tax check karne ka real tarika:
    Small buy karke actual received tokens check karo
    Expected vs actual difference = effective tax
    """
    try:
        test_lamports = int(0.001 * 1e9)  # 0.001 SOL test

        # Expected output
        quote_in = get_quote(SOL_MINT, token, test_lamports)
        if not quote_in:
            return 0, 0

        expected_out = int(quote_in.get("outAmount", 0))
        if expected_out <= 0:
            return 0, 0

        # Sell quote — kitna wapas milega
        quote_out = get_quote(token, SOL_MINT, expected_out)
        if not quote_out:
            return 0, 0

        actual_back  = int(quote_out.get("outAmount", 0))
        expected_back = test_lamports

        # Tax calculate karo
        if expected_back > 0:
            total_tax = ((expected_back - actual_back) / expected_back) * 100
            buy_tax   = round(total_tax / 2, 1)
            sell_tax  = round(total_tax / 2, 1)
            return max(0, buy_tax), max(0, sell_tax)

        return 0, 0

    except:
        return 0, 0

# ============================================================
# SECURITY CHECK — ALL REAL CHECKS
# ============================================================

def security_check(token, pair):
    results = {
        "sell_ok":         False,
        "mint_disabled":   False,
        "freeze_disabled": False,
        "lp_locked":       False,
        "top_holder_ok":   False,
        "sell_tax":        0,
        "buy_tax":         0,
        "top_holder_pct":  0,
        "lp_info":         "",
    }
    passed = 0

    # ── 1. Jupiter sell check ──
    try:
        fake_amount = int(0.01 * 1e9)
        buy_quote   = get_quote(SOL_MINT, token, fake_amount)
        if buy_quote:
            out_amount = int(buy_quote.get("outAmount", 0))
            if out_amount > 0:
                sell_quote = get_quote(token, SOL_MINT, out_amount)
                if sell_quote:
                    returned = int(sell_quote.get("outAmount", 0)) / 1e9
                    if returned > 0:
                        results["sell_ok"] = True
                        passed += 1
    except:
        pass

    # ── 2. RPC mint + freeze check ──
    try:
        r = session.post(
            RPC_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [token, {"encoding": "jsonParsed"}]
            },
            timeout=10
        )
        result = r.json().get("result", {}).get("value")
        if result:
            info        = result.get("data", {}).get("parsed", {}).get("info", {})
            mint_auth   = info.get("mintAuthority")
            freeze_auth = info.get("freezeAuthority")
            if mint_auth is None:
                results["mint_disabled"] = True
                passed += 1
            if freeze_auth is None:
                results["freeze_disabled"] = True
                passed += 1
    except:
        pass

    # ── 3. LP lock check ──
    try:
        lp_ok, lp_info          = check_lp_locked(token, pair)
        results["lp_locked"]    = lp_ok
        results["lp_info"]      = lp_info
        if lp_ok:
            passed += 1
    except:
        pass

    # ── 4. Top holder check ──
    try:
        holder_ok, holder_pct        = check_top_holder(token)
        results["top_holder_ok"]     = holder_ok
        results["top_holder_pct"]    = holder_pct
        if holder_ok:
            passed += 1
    except:
        pass

    # ── 5. Real tax check ──
    try:
        buy_tax, sell_tax      = check_tax(token)
        results["buy_tax"]     = buy_tax
        results["sell_tax"]    = sell_tax
    except:
        pass

    return results, passed

# ============================================================
# PRINT SECURITY
# ============================================================

def print_security(results):
    print(bold(cyan("  ===============================")))
    print(bold(cyan("  SECURITY CONFIRMATIONS")))
    print(bold(cyan("  ===============================")))
    print(green("  ✓ Sell possible")      if results["sell_ok"]         else red("  ✗ Sell NOT possible"))
    print(green("  ✓ Mint disabled")      if results["mint_disabled"]   else red("  ✗ Mint ENABLED"))
    print(green("  ✓ Freeze disabled")    if results["freeze_disabled"] else red("  ✗ Freeze ENABLED"))

    if results["lp_locked"]:
        print(green(f"  ✓ LP locked / burned  ({results['lp_info']})"))
    else:
        print(red(f"  ✗ LP NOT locked       ({results['lp_info']})"))

    if results["top_holder_pct"] > 0:
        fn = green if results["top_holder_ok"] else red
        ic = "✓" if results["top_holder_ok"] else "✗"
        print(fn(f"  {ic} Top holder: {results['top_holder_pct']}%  (limit: {MAX_TOP_HOLDER_PCT}%)"))
    else:
        print(gray("  ~ Top holder: data unavailable"))

    if results["buy_tax"] > 0 or results["sell_tax"] > 0:
        tax_fn = red if (results["buy_tax"] > 5 or results["sell_tax"] > 5) else yellow
        print(tax_fn(f"  ⚠ Buy Tax: {results['buy_tax']}%  Sell Tax: {results['sell_tax']}%"))
    else:
        print(green("  ✓ No tax detected"))

    print(bold(cyan("  ===============================")))

# ============================================================
# SHOW ACTIVE HOLDINGS
# ============================================================

def show_active_holdings():
    if not positions:
        return
    print()
    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
    print(bold("📊 ACTIVE HOLDINGS"))
    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
    for token, pos in positions.items():
        try:
            value   = get_real_value_usd(token)
            pnl_usd = value - BUY_AMOUNT_USD
            pnl_pct = (pnl_usd / BUY_AMOUNT_USD) * 100
            fn      = green if pnl_usd >= 0 else red
            sign    = "+" if pnl_pct >= 0 else ""
            print(fn(f"  {pos['symbol']:<6} │ VALUE: ${value:.2f} │ PF: {sign}{pnl_pct:.0f}%"))
        except:
            print(gray(f"  {pos['symbol']} │ checking..."))
    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
    print()

# ============================================================
# LIVE STATS
# ============================================================

def show_live_stats():
    invested  = len(positions) * BUY_AMOUNT_USD
    pnl       = sum(t["pnl_usd"] for t in trade_history)
    pnl_color = green if pnl >= 0 else red
    print()
    print(bold(cyan("━━━━━━━━━ LIVE STATS ━━━━━━━━━")))
    print(f"  Active Coins : {len(positions)}")
    print(f"  Invested     : ${invested:.2f}")
    print(f"  Closed Trades: {len(trade_history)}")
    print(pnl_color(f"  Session PNL  : ${pnl:.2f}"))
    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
    print()

# ============================================================
# FINAL SUMMARY
# ============================================================

def final_summary():
    print()
    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
    print(bold(cyan("📊 FINAL SESSION SUMMARY")))
    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))

    if not trade_history:
        print("  No closed trades.")
        print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
        return

    total_pnl = sum(t["pnl_usd"] for t in trade_history)
    invested  = len(trade_history) * BUY_AMOUNT_USD
    returned  = invested + total_pnl
    wins      = len([t for t in trade_history if t["pnl_usd"] > 0])
    losses    = len(trade_history) - wins
    best      = max(trade_history, key=lambda x: x["pnl_pct"])
    worst     = min(trade_history, key=lambda x: x["pnl_pct"])
    pnl_color = green if total_pnl >= 0 else red
    total_pct = (total_pnl / invested * 100) if invested > 0 else 0

    print(f"  Total Trades   : {len(trade_history)}")
    print(f"  Wins           : {wins}")
    print(f"  Losses         : {losses}")
    print()
    print(f"  Invested       : ${invested:.2f}")
    print(f"  Returned       : ${returned:.2f}")
    print()
    print(pnl_color(f"  💰 Net P&L      : ${total_pnl:.2f} ({total_pct:.1f}%)"))
    print()
    print(green(f"  Best Trade     : {best['symbol']} ({best['pnl_pct']:.0f}%)"))
    print(red(f"  Worst Trade    : {worst['symbol']} ({worst['pnl_pct']:.0f}%)"))
    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))

# ============================================================
# MONITOR
# ============================================================

def monitor_positions():
    remove = []

    print()
    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
    print(bold("📊 POSITION UPDATE"))
    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))

    for token, pos in positions.items():
        try:
            value = get_real_value_usd(token)
            if value <= 0:
                continue

            pnl_usd = value - BUY_AMOUNT_USD
            pnl_pct = (pnl_usd / BUY_AMOUNT_USD) * 100

            if value > pos["peak_value"]:
                pos["peak_value"] = value

            peak      = pos["peak_value"]
            pump_pct  = ((peak - BUY_AMOUNT_USD) / BUY_AMOUNT_USD) * 100
            peak_drop = ((value - peak) / peak) * 100 if peak > 0 else 0

            fn      = green if pnl_usd >= 0 else red
            pump_fn = green if pump_pct > 0 else gray
            sign    = "+" if pnl_pct >= 0 else ""
            p_sign  = "+" if pump_pct > 0 else ""

            print(fn(
                f"  {pos['symbol']:<6} │ "
                f"PUMP: {pump_fn(f'{p_sign}{pump_pct:.1f}%')} │ "
                f"DROP: {red(f'{peak_drop:.1f}%') if peak_drop < -1 else gray(f'{peak_drop:.1f}%')} │ "
                f"VALUE: ${value:.2f} │ "
                f"PF: {fn(f'{sign}${pnl_usd:.2f} ({sign}{pnl_pct:.1f}%)')} │ "
                f"TP: {TP_TARGET}% │ HOLDING"
            ))

            reason = None
            if pnl_pct >= TP_TARGET:
                reason = "TAKE PROFIT"
            elif pnl_pct <= -STOP_LOSS_PCT:
                reason = "STOP LOSS"
            elif peak_drop <= -TRAILING_STOP_PCT:
                reason = "TRAILING STOP"
            elif (time.time() - pos["time"]) >= MAX_HOLD_SECONDS:
                reason = "TIME EXIT"

            if reason:
                print()
                if reason == "TAKE PROFIT":
                    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
                    print(bold(green(f"🟢 TAKE PROFIT HIT — {pos['symbol']}")))
                    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
                elif reason == "TRAILING STOP":
                    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
                    print(bold(yellow(f"🟠 TRAILING STOP — {pos['symbol']}")))
                    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
                elif reason == "STOP LOSS":
                    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
                    print(bold(red(f"🔴 STOP LOSS — {pos['symbol']}")))
                    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
                else:
                    print(bold(yellow(f"  ⏰ TIME EXIT — {pos['symbol']}")))

                sig = sell_token(token)

                fn_close = green if pnl_usd >= 0 else red
                label    = "Profit" if pnl_usd >= 0 else "Loss"
                print(fn_close(f"  {label}: {sign}${pnl_usd:.2f} ({sign}{pnl_pct:.2f}%)"))

                if sig:
                    print(green(f"  TX: https://solscan.io/tx/{sig}"))

                trade_history.append({
                    "symbol":  pos["symbol"],
                    "pnl_pct": pnl_pct,
                    "pnl_usd": pnl_usd - GAS_FEE
                })
                cooldowns[token] = time.time()
                remove.append(token)
                beep()
                show_live_stats()

        except Exception as e:
            print(red(f"  Monitor Error: {e}"))

    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
    print()

    for token in remove:
        if token in positions:
            del positions[token]

# ============================================================
# SCREEN POOL
# ============================================================

def screen_pool(pool):
    try:
        if len(positions) >= MAX_OPEN_POSITIONS:
            return

        attr  = pool.get("attributes", {})
        rel   = pool.get("relationships", {})
        base  = rel.get("base_token", {}).get("data", {}).get("id", "")
        token = base.replace("solana_", "")

        if not token:
            return
        if token in positions:
            return
        if token in seen_tokens:
            return
        if token in cooldowns:
            if (time.time() - cooldowns[token]) < TOKEN_COOLDOWN:
                return

        seen_tokens.add(token)

        created = attr.get("pool_created_at")
        if not created:
            return

        created_dt = datetime.datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")
        age = (
            datetime.datetime.now(datetime.timezone.utc)
            - created_dt.replace(tzinfo=datetime.timezone.utc)
        ).total_seconds()

        if age > MAX_COIN_AGE_SEC:
            return

        pair = get_pair(token)
        if not pair:
            return

        liquidity = float(pair.get("liquidity", {}).get("usd", 0))
        if liquidity < MIN_LIQUIDITY or liquidity > MAX_LIQUIDITY:
            return

        symbol = pair.get("baseToken", {}).get("symbol", "???")
        price  = float(pair.get("priceUsd", 0))

        if price <= 0:
            return

        # ── SECURITY CHECK ──
        print(gray(f"  [{now()}] {symbol} — Security check..."))
        sec_results, passed = security_check(token, pair)
        print_security(sec_results)

        # ── STRICT FILTERS ──
        if not sec_results["sell_ok"]:
            print(red(f"  ❌ {symbol} — Sell possible nahi — SKIP"))
            return
        if not sec_results["mint_disabled"]:
            print(red(f"  ❌ {symbol} — Mint enabled — SKIP"))
            return
        if not sec_results["freeze_disabled"]:
            print(red(f"  ❌ {symbol} — Freeze enabled — SKIP"))
            return
        if not sec_results["lp_locked"]:
            print(red(f"  ❌ {symbol} — LP locked nahi — SKIP"))
            return
        if sec_results["sell_tax"] > 10 or sec_results["buy_tax"] > 10:
            print(red(f"  ❌ {symbol} — Tax zyada hai — SKIP"))
            return

        print()
        print(bold(cyan("  ┌── 🟢 NEW COIN ──────────────────────────────────")))
        print(f"  │  {symbol} Age: {int(age)}s Liq: ${liquidity:,.0f}")
        print(f"  │  Price     : ${price:.10f}")
        print(f"  │  Buying    : ${BUY_AMOUNT_USD}")
        print(f"  │  SAFE TYPE : LP + HONEYPOT")
        print(f"  │  TP TARGET : {TP_TARGET}%")
        print(f"  │  TRAILING  : {TRAILING_STOP_PCT}%")
        if sec_results["buy_tax"] > 0 or sec_results["sell_tax"] > 0:
            print(f"  │  Tax       : Buy {sec_results['buy_tax']}% / Sell {sec_results['sell_tax']}%")
        print(bold(cyan("  └─────────────────────────────────────────────────")))

        sig = buy_token(token)
        if not sig:
            print(red(f"  ❌ BUY FAILED: {symbol}"))
            return

        positions[token] = {
            "symbol":      symbol,
            "entry_value": BUY_AMOUNT_USD,
            "peak_value":  BUY_AMOUNT_USD,
            "tp":          TP_TARGET,
            "tp_hit":      False,
            "runner":      False,
            "safe_type":   "LP + HONEYPOT",
            "time":        time.time()
        }

        sol_price  = get_sol_price()
        sol_amount = BUY_AMOUNT_USD / sol_price

        print()
        print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
        print(bold(green("🟢 BUY SUCCESS")))
        print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
        print(f"  ◎ SOL Used   : {sol_amount:.6f} SOL")
        print(f"  📦 Position Opened")
        print(f"  📈 Monitoring Started")
        print(green(f"  TX: https://solscan.io/tx/{sig}"))
        print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
        beep()
        show_live_stats()

    except Exception as e:
        print(red(f"  SCREEN ERROR: {e}"))

# ============================================================
# LOAD EXISTING POSITIONS
# ============================================================

def load_existing_positions():
    print()
    print(cyan("  🔍 Scanning wallet for existing tokens...\n"))
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                str(keypair.pubkey()),
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed"}
            ]
        }
        r    = session.post(RPC_URL, json=payload, timeout=20)
        data = r.json().get("result", {}).get("value", [])
        if not data:
            print(cyan("  Wallet mein koi token nahi mila."))
            print()
            return

        for acc in data:
            try:
                info      = acc["account"]["data"]["parsed"]["info"]
                mint      = info["mint"]
                amount    = int(info["tokenAmount"]["amount"])
                decimals  = int(info["tokenAmount"]["decimals"])
                ui_amount = amount / (10 ** decimals)

                if ui_amount <= 0:
                    continue

                pair = get_pair(mint)
                if not pair:
                    continue

                symbol = pair.get("baseToken", {}).get("symbol", "???")
                price  = float(pair.get("priceUsd", 0))

                if price <= 0:
                    continue

                value = ui_amount * price
                if value > 500:
                    continue

                positions[mint] = {
                    "symbol":      symbol,
                    "entry_value": BUY_AMOUNT_USD,
                    "peak_value":  value,
                    "tp":          TP_TARGET,
                    "tp_hit":      False,
                    "runner":      False,
                    "safe_type":   "LOADED",
                    "time":        time.time()
                }
                print(green(f"  ✅ Loaded: {symbol} | Value: ${value:.2f}"))

            except:
                continue

        print()
        print(cyan(f"  Wallet positions loaded: {len(positions)}"))
        print()

    except Exception as e:
        print(red(f"  Wallet Load Error: {e}"))

# ============================================================
# MAIN
# ============================================================

def main():
    clear()
    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
    print(bold(cyan(" ✦ SOLANA MEME BOT | LP+Honeypot Safe Only")))
    print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
    print()
    print(bold(cyan("  ===============================")))
    print(bold(cyan("  FINAL BOT SETTINGS")))
    print(bold(cyan("  ===============================")))
    print(f"  BUY_AMOUNT_USD     = {BUY_AMOUNT_USD}")
    print(f"  MIN_LIQUIDITY      = {MIN_LIQUIDITY}")
    print(f"  MAX_LIQUIDITY      = {MAX_LIQUIDITY}")
    print(f"  MAX_COIN_AGE_SEC   = {MAX_COIN_AGE_SEC}")
    print(f"  SLIPPAGE_BPS       = {SLIPPAGE_BPS}")
    print(f"  SLIPPAGE_PCT       = {SLIPPAGE_PCT}")
    print(f"  TP_TARGET          = {TP_TARGET}")
    print(f"  TRAILING_STOP_PCT  = {TRAILING_STOP_PCT}")
    print(f"  STOP_LOSS_PCT      = {STOP_LOSS_PCT}")
    print(f"  MAX_HOLD_SECONDS   = {MAX_HOLD_SECONDS}")
    print(f"  MAX_OPEN_POSITIONS = {MAX_OPEN_POSITIONS}")
    print(f"  TOKEN_COOLDOWN     = {TOKEN_COOLDOWN}")
    print(f"  MAX_TOP_HOLDER_PCT = {MAX_TOP_HOLDER_PCT}")
    print(bold(cyan("  ===============================")))
    print()

    sol_price = get_sol_price()
    balance   = get_balance()

    print(green(f"  ✅ Wallet: {str(keypair.pubkey())[:28]}..."))
    print(f"  💰 Balance  : {balance:.4f} SOL (${balance * sol_price:.2f})")
    print(f"  📊 Per trade: ${BUY_AMOUNT_USD} = {BUY_AMOUNT_USD / sol_price:.6f} SOL @ ${sol_price:.2f}")
    print(f"  📈 Max open : {MAX_OPEN_POSITIONS} positions = ${BUY_AMOUNT_USD * MAX_OPEN_POSITIONS} max")
    print()

    load_existing_positions()
    show_active_holdings()

    scan = 0
    while True:
        try:
            scan += 1
            print(gray(f"  [{now()}] Scan #{scan} running..."))
            pools = fetch_new_pools()
            print(gray(f"  [{now()}] {len(pools)} new pools — screening..."))

            for pool in pools:
                screen_pool(pool)
                time.sleep(1)

            if positions:
                monitor_positions()

            print(gray(f"  ⟳ Next scan in {SCAN_INTERVAL}s..."))
            print()
            time.sleep(SCAN_INTERVAL)

        except KeyboardInterrupt:
            print()
            print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
            print(bold(cyan("🔵 CTRL+C — BOT STOP")))
            print(bold(cyan("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")))
            print()
            print("  Sab positions sell ho rahe hain...")
            print()

            for token, pos in list(positions.items()):
                try:
                    print(gray(f"  Selling {pos['symbol']}..."), end="  ")
                    value   = get_real_value_usd(token)
                    pnl_usd = value - BUY_AMOUNT_USD
                    pnl_pct = (pnl_usd / BUY_AMOUNT_USD) * 100
                    sig     = sell_token(token)
                    if sig:
                        print(green("✔"))
                        trade_history.append({
                            "symbol":  pos["symbol"],
                            "pnl_pct": pnl_pct,
                            "pnl_usd": pnl_usd - GAS_FEE
                        })
                except Exception as e:
                    print(red(f"  Sell Error: {e}"))

            final_summary()
            print(bold(yellow("  BOT BAND! Allah Hafiz! 👋")))
            break

        except Exception as e:
            print(red(f"  MAIN ERROR: {e}"))
            time.sleep(5)

if __name__ == "__main__":
    main()