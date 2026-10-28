/**
 * ChronosMatch Real-Time Dashboard Client
 */

// Base API URL configuration
// Dynamically targets port 8000 if opened directly from filesystem (file://) or live server ports
const API_BASE = (window.location.protocol === "file:" || (window.location.port !== "8000" && window.location.port !== ""))
    ? "http://127.0.0.1:8000"
    : "";

const STATE = {
    symbol: "AAPL",
    traderId: "TRADER_1",
    side: "BUY",
    orderType: "LIMIT",
    ordersProcessed: 0,
    apiLatencies: [],
    startTime: Date.now(),
    isOnline: false,
};

// DOM Elements
const symbolSelect = document.getElementById("symbolSelect");
const accountSelect = document.getElementById("accountSelect");
const btnSideBuy = document.getElementById("btnSideBuy");
const btnSideSell = document.getElementById("btnSideSell");
const btnTypeLimit = document.getElementById("btnTypeLimit");
const btnTypeMarket = document.getElementById("btnTypeMarket");
const inputPrice = document.getElementById("inputPrice");
const inputQuantity = document.getElementById("inputQuantity");
const groupPrice = document.getElementById("groupPrice");
const btnSubmitOrder = document.getElementById("btnSubmitOrder");
const estOrderTotal = document.getElementById("estOrderTotal");
const lblAvailableCash = document.getElementById("lblAvailableCash");
const lblAvailableShares = document.getElementById("lblAvailableShares");
const orderAlert = document.getElementById("orderAlert");

// Ribbon Elements
const ribbonSymbol = document.getElementById("ribbonSymbol");
const ribbonLastPrice = document.getElementById("ribbonLastPrice");
const ribbonBestBid = document.getElementById("ribbonBestBid");
const ribbonBestAsk = document.getElementById("ribbonBestAsk");
const ribbonSpread = document.getElementById("ribbonSpread");
const ribbonVolume = document.getElementById("ribbonVolume");
const ribbonTradesCount = document.getElementById("ribbonTradesCount");

// Order Book Elements
const obSymbolTitle = document.getElementById("obSymbolTitle");
const obAsksList = document.getElementById("obAsksList");
const obBidsList = document.getElementById("obBidsList");
const obMidSpread = document.getElementById("obMidSpread");

// Account & Portfolio Elements
const accCashBalance = document.getElementById("accCashBalance");
const accReservedCash = document.getElementById("accReservedCash");
const accAvailableCash = document.getElementById("accAvailableCash");
const accTotalPortfolio = document.getElementById("accTotalPortfolio");
const holdingsTbody = document.getElementById("holdingsTbody");
const activeOrdersTbody = document.getElementById("activeOrdersTbody");
const lblActiveOrdersCount = document.getElementById("lblActiveOrdersCount");

// Telemetry Elements
const perfOrdersCount = document.getElementById("perfOrdersCount");
const perfThroughput = document.getElementById("perfThroughput");
const perfAvgLatency = document.getElementById("perfAvgLatency");
const tradesTbody = document.getElementById("tradesTbody");
const lblRecentTradesCount = document.getElementById("lblRecentTradesCount");

// Status & Offline Banner Elements
const systemStatusBadge = document.getElementById("systemStatusBadge");
const engineStatusText = document.getElementById("engineStatusText");
const offlineBanner = document.getElementById("offlineBanner");
const btnRetryConnection = document.getElementById("btnRetryConnection");

// Modals
const modalAccount = document.getElementById("modalAccount");
const btnNewAccountModal = document.getElementById("btnNewAccountModal");
const btnCloseAccModal = document.getElementById("btnCloseAccModal");
const btnCancelAccModal = document.getElementById("btnCancelAccModal");
const formNewAccount = document.getElementById("formNewAccount");

const modalDeposit = document.getElementById("modalDeposit");
const btnDepositModal = document.getElementById("btnDepositModal");
const btnCloseDepModal = document.getElementById("btnCloseDepModal");
const btnCancelDepModal = document.getElementById("btnCancelDepModal");
const formDeposit = document.getElementById("formDeposit");

// Helper: Get currency prefix
function getCurrencyPrefix(sym) {
    if (["TCS", "INFY", "RELIANCE"].includes(sym)) return "₹";
    return "$";
}

// Health Check
async function checkEngineHealth() {
    try {
        const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
        if (res.ok) {
            const data = await res.json();
            if (data.status === "healthy") {
                setEngineOnline(true);
                return true;
            }
        }
        setEngineOnline(false);
        return false;
    } catch (e) {
        setEngineOnline(false);
        return false;
    }
}

function setEngineOnline(online) {
    STATE.isOnline = online;
    const statusDot = document.querySelector(".status-dot");

    if (online) {
        if (systemStatusBadge) systemStatusBadge.classList.remove("offline");
        if (statusDot) statusDot.classList.remove("offline");
        if (engineStatusText) engineStatusText.textContent = "ENGINE ONLINE";
        if (offlineBanner) offlineBanner.classList.add("hidden");
    } else {
        if (systemStatusBadge) systemStatusBadge.classList.add("offline");
        if (statusDot) statusDot.classList.add("offline");
        if (engineStatusText) engineStatusText.textContent = "ENGINE OFFLINE";
        if (offlineBanner) offlineBanner.classList.remove("hidden");
    }
}

// Initialization
document.addEventListener("DOMContentLoaded", async () => {
    setupEventListeners();
    const online = await checkEngineHealth();
    if (online) {
        await initializeDefaultAccounts();
        await refreshMarketAndBook();
        await refreshAccountData();
    }
    startPollingLoop();
});

function setupEventListeners() {
    symbolSelect.addEventListener("change", (e) => {
        STATE.symbol = e.target.value;
        ribbonSymbol.textContent = STATE.symbol;
        obSymbolTitle.textContent = STATE.symbol;
        updateOrderEstimate();
        refreshMarketAndBook();
        refreshAccountData();
    });

    accountSelect.addEventListener("change", (e) => {
        STATE.traderId = e.target.value;
        refreshAccountData();
    });

    btnSideBuy.addEventListener("click", () => setOrderSide("BUY"));
    btnSideSell.addEventListener("click", () => setOrderSide("SELL"));

    btnTypeLimit.addEventListener("click", () => setOrderType("LIMIT"));
    btnTypeMarket.addEventListener("click", () => setOrderType("MARKET"));

    inputPrice.addEventListener("input", updateOrderEstimate);
    inputQuantity.addEventListener("input", updateOrderEstimate);

    document.getElementById("orderForm").addEventListener("submit", handleOrderSubmit);

    if (btnRetryConnection) {
        btnRetryConnection.addEventListener("click", async () => {
            btnRetryConnection.textContent = "Checking...";
            const ok = await checkEngineHealth();
            if (ok) {
                await initializeDefaultAccounts();
                await refreshMarketAndBook();
                await refreshAccountData();
            }
            btnRetryConnection.textContent = "Retry Connection";
        });
    }

    // Modal controls
    btnNewAccountModal.addEventListener("click", () => modalAccount.classList.remove("hidden"));
    btnCloseAccModal.addEventListener("click", () => modalAccount.classList.add("hidden"));
    btnCancelAccModal.addEventListener("click", () => modalAccount.classList.add("hidden"));
    formNewAccount.addEventListener("submit", handleCreateAccount);

    btnDepositModal.addEventListener("click", () => modalDeposit.classList.remove("hidden"));
    btnCloseDepModal.addEventListener("click", () => modalDeposit.classList.add("hidden"));
    btnCancelDepModal.addEventListener("click", () => modalDeposit.classList.add("hidden"));
    formDeposit.addEventListener("submit", handleDeposit);
}

function setOrderSide(side) {
    STATE.side = side;
    if (side === "BUY") {
        btnSideBuy.className = "side-btn active-buy";
        btnSideSell.className = "side-btn";
        btnSubmitOrder.className = "btn btn-buy btn-block";
        btnSubmitOrder.textContent = `PLACE ${STATE.orderType} BUY`;
    } else {
        btnSideBuy.className = "side-btn";
        btnSideSell.className = "side-btn active-sell";
        btnSubmitOrder.className = "btn btn-sell btn-block";
        btnSubmitOrder.textContent = `PLACE ${STATE.orderType} SELL`;
    }
}

function setOrderType(type) {
    STATE.orderType = type;
    if (type === "LIMIT") {
        btnTypeLimit.classList.add("active");
        btnTypeMarket.classList.remove("active");
        groupPrice.classList.remove("hidden");
        inputPrice.required = true;
    } else {
        btnTypeLimit.classList.remove("active");
        btnTypeMarket.classList.add("active");
        groupPrice.classList.add("hidden");
        inputPrice.required = false;
    }
    btnSubmitOrder.textContent = `PLACE ${STATE.orderType} ${STATE.side}`;
    updateOrderEstimate();
}

function updateOrderEstimate() {
    const cur = getCurrencyPrefix(STATE.symbol);
    const qty = parseFloat(inputQuantity.value) || 0;
    const px = STATE.orderType === "LIMIT" ? (parseFloat(inputPrice.value) || 0) : 0;
    if (STATE.orderType === "LIMIT") {
        estOrderTotal.textContent = `${cur}${(qty * px).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    } else {
        estOrderTotal.textContent = `Best Market Available`;
    }
}

async function initializeDefaultAccounts() {
    try {
        const res = await fetch(`${API_BASE}/accounts`);
        if (!res.ok) return;
        const accounts = await res.json();
        if (!accounts || accounts.length === 0) {
            // Seed initial demo accounts
            await createAccountAPI("TRADER_1", 100000.0);
            await createAccountAPI("TRADER_2", 100000.0);
        }
        await populateAccountDropdown();
    } catch (e) {
        console.error("Error initializing accounts:", e);
    }
}

async function createAccountAPI(accountId, initialCash) {
    return fetch(`${API_BASE}/accounts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_id: accountId, initial_cash: initialCash }),
    });
}

async function populateAccountDropdown() {
    try {
        const res = await fetch(`${API_BASE}/accounts`);
        if (!res.ok) return;
        const accounts = await res.json();
        accountSelect.innerHTML = "";
        accounts.forEach((acc) => {
            const opt = document.createElement("option");
            opt.value = acc.account_id;
            opt.textContent = `${acc.account_id} ($${acc.cash_balance.toLocaleString()})`;
            if (acc.account_id === STATE.traderId) opt.selected = true;
            accountSelect.appendChild(opt);
        });
        if (accounts.length > 0 && !STATE.traderId) {
            STATE.traderId = accounts[0].account_id;
        }
    } catch (e) {
        console.error("Failed to populate accounts:", e);
    }
}

async function handleCreateAccount(e) {
    e.preventDefault();
    const accId = document.getElementById("inputNewAccountId").value.trim();
    const cash = parseFloat(document.getElementById("inputInitialCash").value) || 0;

    try {
        const res = await createAccountAPI(accId, cash);
        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || "Failed to create account");
            return;
        }
        modalAccount.classList.add("hidden");
        document.getElementById("inputNewAccountId").value = "";
        STATE.traderId = accId;
        await populateAccountDropdown();
        await refreshAccountData();
    } catch (err) {
        alert("Error connecting to server");
    }
}

async function handleDeposit(e) {
    e.preventDefault();
    const amount = parseFloat(document.getElementById("inputDepositAmount").value) || 0;
    try {
        const res = await fetch(`${API_BASE}/accounts/${STATE.traderId}/deposit`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ amount }),
        });
        if (res.ok) {
            modalDeposit.classList.add("hidden");
            await populateAccountDropdown();
            await refreshAccountData();
        } else {
            const err = await res.json();
            alert(err.detail || "Deposit failed");
        }
    } catch (err) {
        alert("Error depositing funds");
    }
}

async function handleOrderSubmit(e) {
    e.preventDefault();
    const qty = parseInt(inputQuantity.value, 10);
    const px = STATE.orderType === "LIMIT" ? parseFloat(inputPrice.value) : null;

    if (!qty || qty <= 0) {
        showAlert("Quantity must be a positive integer", "error");
        return;
    }
    if (STATE.orderType === "LIMIT" && (!px || px <= 0)) {
        showAlert("Price must be > 0 for Limit Orders", "error");
        return;
    }

    const payload = {
        trader_id: STATE.traderId,
        symbol: STATE.symbol,
        side: STATE.side,
        order_type: STATE.orderType,
        quantity: qty,
        price: px,
    };

    const t0 = performance.now();
    let data;
    try {
        const res = await fetch(`${API_BASE}/orders`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const latencyMs = performance.now() - t0;
        recordLatency(latencyMs);

        data = await res.json();
        if (!res.ok) {
            showAlert(data.detail || "Order rejected by matching engine", "error");
            return;
        }

        setEngineOnline(true);
        STATE.ordersProcessed++;
        perfOrdersCount.textContent = STATE.ordersProcessed.toLocaleString();

        const numTrades = data.trades ? data.trades.length : 0;
        if (numTrades > 0) {
            showAlert(`Order executed! ${numTrades} trade(s) filled instantly.`, "success");
        } else {
            showAlert(`Order resting in book [ID: ${data.order_id}]`, "success");
        }

        // Reset form inputs
        inputQuantity.value = "";
        updateOrderEstimate();
    } catch (err) {
        console.error("Order submit network failure:", err);
        setEngineOnline(false);
        showAlert(`Failed to connect to matching engine at ${API_BASE || '127.0.0.1:8000'}. Please ensure backend is running.`, "error");
        return;
    }

    // Refresh UI non-critically
    try {
        await refreshMarketAndBook();
        await refreshAccountData();
    } catch (err) {
        console.warn("Post-order refresh non-critical error:", err);
    }
}

function recordLatency(latencyMs) {
    const latUs = Math.round(latencyMs * 1000);
    STATE.apiLatencies.push(latUs);
    if (STATE.apiLatencies.length > 50) STATE.apiLatencies.shift();
    const avg = Math.round(STATE.apiLatencies.reduce((a, b) => a + b, 0) / STATE.apiLatencies.length);
    perfAvgLatency.textContent = `${avg} μs`;

    // Throughput
    const elapsedSec = (Date.now() - STATE.startTime) / 1000;
    if (elapsedSec > 0 && STATE.ordersProcessed > 0) {
        const tput = (STATE.ordersProcessed / elapsedSec).toFixed(1);
        perfThroughput.textContent = `${tput} ord/s`;
    }
}

function showAlert(msg, type) {
    orderAlert.textContent = msg;
    orderAlert.className = `alert-box ${type}`;
    orderAlert.classList.remove("hidden");
    setTimeout(() => {
        orderAlert.classList.add("hidden");
    }, 4500);
}

// Data Polling Loop
function startPollingLoop() {
    setInterval(async () => {
        const ok = await checkEngineHealth();
        if (ok) {
            await refreshMarketAndBook();
            await refreshAccountData();
        }
    }, 1000);
}

async function refreshMarketAndBook() {
    const cur = getCurrencyPrefix(STATE.symbol);
    try {
        // 1. Market Summary
        const resMarket = await fetch(`${API_BASE}/market/${STATE.symbol}`);
        if (resMarket.ok) {
            const m = await resMarket.json();
            ribbonLastPrice.textContent = m.last_traded_price ? `${cur}${m.last_traded_price.toFixed(2)}` : "--";
            ribbonBestBid.textContent = m.best_bid ? `${cur}${m.best_bid.toFixed(2)}` : "--";
            ribbonBestAsk.textContent = m.best_ask ? `${cur}${m.best_ask.toFixed(2)}` : "--";
            ribbonSpread.textContent = m.spread !== null ? `${cur}${m.spread.toFixed(2)}` : "--";
            ribbonVolume.textContent = m.total_traded_volume ? m.total_traded_volume.toLocaleString() : "0";
            ribbonTradesCount.textContent = m.total_trades_count ? m.total_trades_count.toLocaleString() : "0";
        }

        // 2. Order Book Depth
        const resOb = await fetch(`${API_BASE}/orderbook/${STATE.symbol}?depth=10`);
        if (resOb.ok) {
            const ob = await resOb.json();
            renderOrderBook(ob, cur);
        }

        // 3. Recent Trades
        const resTrades = await fetch(`${API_BASE}/trades?symbol=${STATE.symbol}&limit=20`);
        if (resTrades.ok) {
            const trades = await resTrades.json();
            renderRecentTrades(trades, cur);
        }
    } catch (e) {
        console.error("Error refreshing market data:", e);
    }
}

function renderOrderBook(ob, cur) {
    obMidSpread.textContent = ob.spread !== null ? `${cur}${ob.spread.toFixed(2)}` : "EMPTY";

    // Calculate max volume for visual depth bars
    let maxVol = 1;
    if (ob.bids) ob.bids.forEach((b) => { if (b.quantity > maxVol) maxVol = b.quantity; });
    if (ob.asks) ob.asks.forEach((a) => { if (a.quantity > maxVol) maxVol = a.quantity; });

    // Render Asks (descending so highest is at top, lowest ask right above spread)
    if (!ob.asks || ob.asks.length === 0) {
        obAsksList.innerHTML = `<div class="empty-book">No active asks</div>`;
    } else {
        const asksReversed = [...ob.asks].reverse();
        obAsksList.innerHTML = asksReversed.map((a) => {
            const depthPct = Math.min(100, Math.round((a.quantity / maxVol) * 100));
            return `
                <div class="book-row ask-row">
                    <div class="depth-bar depth-bar-ask" style="width: ${depthPct}%;"></div>
                    <span class="row-price font-bold">${cur}${a.price.toFixed(2)}</span>
                    <span class="row-qty font-mono">${a.quantity.toLocaleString()}</span>
                    <span class="row-count font-mono text-muted">${a.order_count}</span>
                </div>
            `;
        }).join("");
    }

    // Render Bids (highest price at top, right below spread)
    if (!ob.bids || ob.bids.length === 0) {
        obBidsList.innerHTML = `<div class="empty-book">No active bids</div>`;
    } else {
        obBidsList.innerHTML = ob.bids.map((b) => {
            const depthPct = Math.min(100, Math.round((b.quantity / maxVol) * 100));
            return `
                <div class="book-row bid-row">
                    <div class="depth-bar depth-bar-bid" style="width: ${depthPct}%;"></div>
                    <span class="row-price font-bold">${cur}${b.price.toFixed(2)}</span>
                    <span class="row-qty font-mono">${b.quantity.toLocaleString()}</span>
                    <span class="row-count font-mono text-muted">${b.order_count}</span>
                </div>
            `;
        }).join("");
    }
}

function renderRecentTrades(trades, cur) {
    lblRecentTradesCount.textContent = trades.length;
    if (!trades || trades.length === 0) {
        tradesTbody.innerHTML = `<tr><td colspan="5" class="empty-state">No trades executed yet</td></tr>`;
        return;
    }

    tradesTbody.innerHTML = trades.map((t) => {
        const timeStr = new Date(t.timestamp * 1000).toLocaleTimeString();
        return `
            <tr>
                <td class="font-mono text-muted">${t.trade_id.slice(-8)}</td>
                <td class="font-mono">${timeStr}</td>
                <td class="font-mono font-bold text-buy">${cur}${t.execution_price.toFixed(2)}</td>
                <td class="font-mono">${t.quantity.toLocaleString()}</td>
                <td class="font-mono text-muted">${cur}${(t.execution_price * t.quantity).toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
            </tr>
        `;
    }).join("");
}

async function refreshAccountData() {
    if (!STATE.traderId) return;
    const cur = getCurrencyPrefix(STATE.symbol);

    try {
        // 1. Portfolio & Cash
        const resPort = await fetch(`${API_BASE}/portfolio/${STATE.traderId}`);
        if (resPort.ok) {
            const p = await resPort.json();
            accCashBalance.textContent = `$${p.cash_balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
            accReservedCash.textContent = `$${p.reserved_cash.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
            accAvailableCash.textContent = `$${p.available_cash.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
            accTotalPortfolio.textContent = `$${p.total_portfolio_value.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;

            lblAvailableCash.textContent = `$${p.available_cash.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;

            // Check current symbol holding
            let curShares = 0;
            const curH = p.holdings.find((h) => h.symbol === STATE.symbol);
            if (curH) curShares = curH.available_quantity;
            lblAvailableShares.textContent = curShares.toLocaleString();

            renderHoldings(p.holdings);
        }

        // 2. Active Orders for this trader
        const resOrders = await fetch(`${API_BASE}/orders?trader_id=${STATE.traderId}`);
        if (resOrders.ok) {
            const orders = await resOrders.json();
            const active = orders.filter((o) => o.status === "PENDING" || o.status === "PARTIALLY_FILLED");
            renderActiveOrders(active, cur);
        }
    } catch (e) {
        console.error("Error refreshing account data:", e);
    }
}

function renderHoldings(holdings) {
    if (!holdings || holdings.length === 0) {
        holdingsTbody.innerHTML = `<tr><td colspan="5" class="empty-state">No stock holdings</td></tr>`;
        return;
    }

    holdingsTbody.innerHTML = holdings.map((h) => {
        const cur = getCurrencyPrefix(h.symbol);
        const pnlClass = h.unrealized_pnl >= 0 ? "text-buy" : "text-sell";
        const sign = h.unrealized_pnl >= 0 ? "+" : "";
        return `
            <tr>
                <td class="font-mono font-bold">${h.symbol}</td>
                <td class="font-mono">${h.quantity.toLocaleString()}</td>
                <td class="font-mono">${cur}${h.average_buy_price.toFixed(2)}</td>
                <td class="font-mono">${cur}${h.market_value.toFixed(2)}</td>
                <td class="font-mono ${pnlClass}">${sign}${cur}${h.unrealized_pnl.toFixed(2)} (${sign}${h.unrealized_pnl_percent}%)</td>
            </tr>
        `;
    }).join("");
}

function renderActiveOrders(orders, cur) {
    lblActiveOrdersCount.textContent = orders.length;
    if (!orders || orders.length === 0) {
        activeOrdersTbody.innerHTML = `<tr><td colspan="5" class="empty-state">No resting orders for current trader</td></tr>`;
        return;
    }

    activeOrdersTbody.innerHTML = orders.map((o) => {
        const sideClass = o.side === "BUY" ? "text-buy" : "text-sell";
        return `
            <tr>
                <td class="font-mono text-muted">${o.order_id}</td>
                <td class="font-mono font-bold ${sideClass}">${o.side}</td>
                <td class="font-mono">${cur}${o.price ? o.price.toFixed(2) : 'MKT'}</td>
                <td class="font-mono">${o.remaining_quantity}/${o.quantity}</td>
                <td>
                    <button class="btn btn-cancel" onclick="cancelOrder('${o.order_id}')">Cancel</button>
                </td>
            </tr>
        `;
    }).join("");
}

window.cancelOrder = async function (orderId) {
    if (!confirm(`Cancel order ${orderId}?`)) return;
    try {
        const res = await fetch(`${API_BASE}/orders/${orderId}`, { method: "DELETE" });
        if (res.ok) {
            showAlert(`Order ${orderId} cancelled`, "success");
            await refreshMarketAndBook();
            await refreshAccountData();
        } else {
            const err = await res.json();
            showAlert(err.detail || "Cancellation failed", "error");
        }
    } catch (e) {
        showAlert("Error cancelling order", "error");
    }
};
