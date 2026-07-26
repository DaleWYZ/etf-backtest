/** ETF 定投回测工具 — 前端逻辑 */

// ===== 全局状态 =====
const state = {
    selectedEtfs: new Map(), // code -> name
    backtestResults: {}, // code -> result
    currentTab: null, // 当前显示结果的 ETF code
    chartInstance: null,
    compareChartInstance: null,
    abortController: null,
};

// ===== 初始化 =====
document.addEventListener("DOMContentLoaded", () => {
    initDateDefaults();
    initPresetEtfs();
    initFrequencyToggle();
    initMonthDaySelect();
    initEventListeners();
    // 默认选中标普500ETF
    toggleEtf("513500", "标普500ETF(博时)");

    // 浏览器关闭时通知后端退出
    window.addEventListener("beforeunload", () => {
        navigator.sendBeacon("/api/shutdown");
    });
});

function initDateDefaults() {
    const today = new Date();
    const fiveYearsAgo = new Date(today);
    fiveYearsAgo.setFullYear(today.getFullYear() - 5);

    document.getElementById("start-date").value = formatDate(fiveYearsAgo);
    document.getElementById("end-date").value = formatDate(today);
}

function formatDate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
}

// ===== 预设 ETF =====
function initPresetEtfs() {
    fetch("/api/etf/presets")
        .then((r) => r.json())
        .then((data) => {
            const container = document.getElementById("etf-presets");
            if (!data.groups) return;

            container.innerHTML = data.groups
                .map(
                    (group) => `
                <div class="etf-group">
                    <div class="etf-group-name">${group.name}</div>
                    <div class="etf-checkboxes">
                        ${group.etfs
                            .map(
                                (etf) => `
                            <label class="etf-checkbox" data-code="${etf.code}" data-name="${etf.name}">
                                <span class="check-icon">✓</span>
                                <input type="checkbox" value="${etf.code}">
                                ${etf.code} ${etf.name}
                            </label>
                        `
                            )
                            .join("")}
                    </div>
                </div>
            `
                )
                .join("");

            // 绑定点击事件
            container.querySelectorAll(".etf-checkbox").forEach((label) => {
                label.addEventListener("click", (e) => {
                    e.preventDefault();
                    const code = label.dataset.code;
                    const name = label.dataset.name;
                    toggleEtf(code, name);
                    label.classList.toggle("checked", state.selectedEtfs.has(code));
                });
            });
        })
        .catch((err) => {
            console.error("获取预设ETF失败:", err);
        });
}

// ===== ETF 选择 =====
function toggleEtf(code, name) {
    if (state.selectedEtfs.has(code)) {
        state.selectedEtfs.delete(code);
    } else {
        state.selectedEtfs.set(code, name);
    }
    renderSelectedEtfs();
}

function renderSelectedEtfs() {
    const container = document.getElementById("selected-etfs");
    if (state.selectedEtfs.size === 0) {
        container.innerHTML = '<span style="color: #aab2bd;font-size:13px;">选择ETF或输入代码...</span>';
        return;
    }

    container.innerHTML = Array.from(state.selectedEtfs.entries())
        .map(
            ([code, name]) => `
            <div class="chip" data-code="${code}">
                ${name}(${code}) <span class="chip-remove" data-code="${code}">&times;</span>
            </div>
        `
        )
        .join("");

    // 绑定删除事件
    container.querySelectorAll(".chip-remove").forEach((el) => {
        el.addEventListener("click", (e) => {
            e.stopPropagation();
            const code = el.dataset.code;
            state.selectedEtfs.delete(code);
            // 同步取消 checkbox
            const checkbox = document.querySelector(`.etf-checkbox[data-code="${code}"]`);
            if (checkbox) checkbox.classList.remove("checked");
            renderSelectedEtfs();
            clearResults();
        });
    });

    // 同步 checkbox 状态
    document.querySelectorAll(".etf-checkbox").forEach((cb) => {
        cb.classList.toggle("checked", state.selectedEtfs.has(cb.dataset.code));
    });
}

// ===== 搜索 ETF =====
async function searchEtf(keyword) {
    const resultsDiv = document.getElementById("search-results");
    if (!keyword || keyword.length < 2) {
        resultsDiv.classList.add("hidden");
        return;
    }

    try {
        const resp = await fetch(`/api/etf/search?keyword=${encodeURIComponent(keyword)}`);
        const data = await resp.json();
        resultsDiv.classList.remove("hidden");
        if (!data.results || data.results.length === 0) {
            resultsDiv.innerHTML =
                '<div style="padding:8px;font-size:12px;color:#999;">未找到匹配的ETF</div>';
            return;
        }
        resultsDiv.innerHTML = data.results
            .map(
                (r) => `
            <div class="search-result-item" data-code="${r.code}" data-name="${r.name}">
                <span>${r.code} ${r.name}</span>
                <span class="add-icon">+</span>
            </div>
        `
            )
            .join("");

        resultsDiv.querySelectorAll(".search-result-item").forEach((item) => {
            item.addEventListener("click", () => {
                toggleEtf(item.dataset.code, item.dataset.name);
                resultsDiv.classList.add("hidden");
                document.getElementById("custom-code").value = "";
            });
        });
    } catch (err) {
        console.error("搜索失败:", err);
    }
}

// ===== 定投频率切换 =====
function initFrequencyToggle() {
    const freqSelect = document.getElementById("frequency");
    const weeklyOpts = document.getElementById("weekly-options");
    const monthlyOpts = document.getElementById("monthly-options");

    freqSelect.addEventListener("change", () => {
        weeklyOpts.style.display = freqSelect.value === "weekly" ? "flex" : "none";
        monthlyOpts.style.display = freqSelect.value === "monthly" ? "flex" : "none";
    });
}

function initMonthDaySelect() {
    const select = document.getElementById("month-day");
    for (let i = 1; i <= 28; i++) {
        const opt = document.createElement("option");
        opt.value = i;
        opt.textContent = `每月${i}号`;
        select.appendChild(opt);
    }
}

// ===== 事件监听 =====
function initEventListeners() {
    // 日期快捷按钮
    document.querySelectorAll(".shortcut-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            document
                .querySelectorAll(".shortcut-btn")
                .forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");

            const years = btn.dataset.years;
            const endDate = document.getElementById("end-date").value;
            const end = endDate ? new Date(endDate) : new Date();
            const start = new Date(end);

            if (years === "all") {
                start.setFullYear(2000);
            } else {
                start.setFullYear(end.getFullYear() - parseInt(years));
            }
            document.getElementById("start-date").value = formatDate(start);
        });
    });

    // 搜索
    const searchInput = document.getElementById("custom-code");
    let searchTimeout;
    searchInput.addEventListener("input", () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => searchEtf(searchInput.value.trim()), 400);
    });
    document.getElementById("search-btn").addEventListener("click", () => {
        searchEtf(searchInput.value.trim());
    });

    // 开始回测
    document.getElementById("run-btn").addEventListener("click", runAllBacktests);

    // 日志面板
    initLogPanel();

    // 点击结果面板空白处关闭搜索结果
    document.addEventListener("click", (e) => {
        const resultsDiv = document.getElementById("search-results");
        if (!e.target.closest("#search-results") && !e.target.closest("#custom-code")) {
            resultsDiv.classList.add("hidden");
        }
    });
}

// ===== 回测执行 =====
async function runAllBacktests() {
    if (state.selectedEtfs.size === 0) {
        showStatus("请先选择 ETF", "error");
        return;
    }

    const startDate = document.getElementById("start-date").value;
    const endDate = document.getElementById("end-date").value;
    const amount = parseFloat(document.getElementById("amount").value);
    const frequency = document.getElementById("frequency").value;
    const weekday = parseInt(document.getElementById("weekday").value);
    const monthDay = parseInt(document.getElementById("month-day").value);
    const feeRate = parseFloat(document.getElementById("fee-rate").value) / 100;

    if (!startDate || !endDate) {
        showStatus("请选择回测时间范围", "error");
        return;
    }
    if (amount <= 0) {
        showStatus("定投金额必须大于0", "error");
        return;
    }

    setRunning(true);
    state.backtestResults = {};
    clearResults();

    const codes = Array.from(state.selectedEtfs.keys());
    let completed = 0;

    try {
        for (const code of codes) {
            showStatus(`正在回测 ${code} (${++completed}/${codes.length})...`, "");

            const resp = await fetch("/api/backtest", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    etf_code: code,
                    start_date: startDate,
                    end_date: endDate,
                    amount: amount,
                    frequency: frequency,
                    weekday: weekday,
                    month_day: monthDay,
                    fee_rate: feeRate,
                }),
            });

            const data = await resp.json();
            if (!resp.ok) {
                throw new Error(data.error || `回测 ${code} 失败`);
            }
            state.backtestResults[code] = data;
        }

        showStatus(`完成！共回测 ${completed} 只 ETF`, "");
        renderResults();
    } catch (err) {
        showStatus(err.message, "error");
    } finally {
        setRunning(false);
    }
}

function setRunning(running) {
    const runBtn = document.getElementById("run-btn");
    const stopBtn = document.getElementById("stop-btn");
    const progress = document.getElementById("progress-bar");

    if (running) {
        runBtn.classList.add("hidden");
        stopBtn.classList.remove("hidden");
        progress.classList.remove("hidden");
        progress.classList.add("active");
    } else {
        runBtn.classList.remove("hidden");
        stopBtn.classList.add("hidden");
        progress.classList.add("hidden");
        progress.classList.remove("active");
    }
}

function showStatus(msg, type) {
    const el = document.getElementById("status-msg");
    el.textContent = msg;
    el.className = "status-msg";
    if (type) el.classList.add(type);
    if (type === "error") {
        el.textContent = msg + "  点击右上角 📋日志 查看详情";
    }
}

function clearResults() {
    document.getElementById("empty-state").classList.remove("hidden");
    document.getElementById("result-content").classList.add("hidden");
    document.getElementById("result-tabs").classList.add("hidden");
    document.getElementById("compare-content").classList.add("hidden");
    state.backtestResults = {};
    state.currentTab = null;
}

// ===== 渲染结果 =====
function renderResults() {
    const codes = Object.keys(state.backtestResults);
    if (codes.length === 0) return;

    document.getElementById("empty-state").classList.add("hidden");

    if (codes.length === 1) {
        // 单 ETF：显示详细结果
        document.getElementById("result-tabs").classList.add("hidden");
        document.getElementById("compare-content").classList.add("hidden");
        renderSingleResult(state.backtestResults[codes[0]]);
    } else {
        // 多 ETF：Tab + 对比
        renderTabs(codes);
        renderCompareTable();
        renderCompareChart();
        // 默认显示第一个
        switchTab(codes[0]);
    }
}

function renderTabs(codes) {
    const tabsContainer = document.getElementById("result-tabs");
    tabsContainer.classList.remove("hidden");
    tabsContainer.innerHTML = codes
        .map(
            (code, i) => `
        <button class="result-tab ${i === 0 ? "active" : ""}" data-code="${code}">
            ${state.backtestResults[code].etf_name}
        </button>
    `
        )
        .join("");

    tabsContainer.querySelectorAll(".result-tab").forEach((tab) => {
        tab.addEventListener("click", () => switchTab(tab.dataset.code));
    });
}

function switchTab(code) {
    state.currentTab = code;
    document.querySelectorAll(".result-tab").forEach((t) => t.classList.remove("active"));
    const activeTab = document.querySelector(`.result-tab[data-code="${code}"]`);
    if (activeTab) activeTab.classList.add("active");

    document.getElementById("result-content").classList.remove("hidden");
    document.getElementById("compare-content").classList.add("hidden");
    renderSingleResult(state.backtestResults[code]);
}

function renderSingleResult(result) {
    document.getElementById("result-content").classList.remove("hidden");

    // 指标卡片
    const cards = [
        { label: "总投入", value: `¥${result.total_invested.toLocaleString()}` },
        {
            label: "最终市值",
            value: `¥${result.final_value.toLocaleString()}`,
            cls: result.final_value >= result.total_invested ? "positive" : "negative",
        },
        {
            label: "总收益",
            value: `¥${result.total_return.toLocaleString()}`,
            cls: result.total_return >= 0 ? "positive" : "negative",
        },
        {
            label: "总收益率",
            value: `${(result.total_return_rate * 100).toFixed(2)}%`,
            cls: result.total_return_rate >= 0 ? "positive" : "negative",
            primary: true,
        },
        { label: "年化收益 (CAGR)", value: `${(result.cagr * 100).toFixed(2)}%` },
        { label: "最大回撤", value: `${(result.max_drawdown * 100).toFixed(2)}%` },
        { label: "夏普比率", value: result.sharpe_ratio.toFixed(2) },
        { label: "胜率", value: `${(result.win_rate * 100).toFixed(1)}%` },
        { label: "XIRR", value: `${(result.xirr * 100).toFixed(2)}%` },
        { label: "定投次数", value: `${result.investment_count} 次` },
    ];

    document.getElementById("metrics-cards").innerHTML = cards
        .map(
            (c) => `
        <div class="metric-card ${c.primary ? "primary-card" : ""}">
            <div class="metric-label">${c.label}</div>
            <div class="metric-value ${c.cls || ""}">${c.value}</div>
        </div>
    `
        )
        .join("");

    // 年度表格
    const tbody = document.querySelector("#annual-table tbody");
    tbody.innerHTML = "";
    if (result.annual_details && result.annual_details.length > 0) {
        result.annual_details.forEach((row) => {
            const tr = document.createElement("tr");
            const retCls = row.return >= 0 ? "return-positive" : "return-negative";
            tr.innerHTML = `
                <td>${row.year}</td>
                <td>¥${row.invested.toLocaleString()}</td>
                <td>¥${row.start_value.toLocaleString()}</td>
                <td>¥${row.end_value.toLocaleString()}</td>
                <td class="${retCls}">¥${row.return.toLocaleString()}</td>
                <td class="${retCls}">${(row.return_rate * 100).toFixed(2)}%</td>
            `;
            tbody.appendChild(tr);
        });

        // 添加汇总行
        const sumTr = document.createElement("tr");
        sumTr.style.fontWeight = "600";
        sumTr.style.borderTop = "2px solid #e1e5eb";
        sumTr.innerHTML = `
            <td>合计</td>
            <td>¥${result.total_invested.toLocaleString()}</td>
            <td>-</td>
            <td>¥${result.final_value.toLocaleString()}</td>
            <td class="${result.total_return >= 0 ? "return-positive" : "return-negative"}">
                ¥${result.total_return.toLocaleString()}
            </td>
            <td class="${result.total_return_rate >= 0 ? "return-positive" : "return-negative"}">
                ${(result.total_return_rate * 100).toFixed(2)}%
            </td>
        `;
        tbody.appendChild(sumTr);
    }

    // 收益曲线
    renderChart(result);
}

// ===== 图表 =====
function renderChart(result) {
    if (state.chartInstance) {
        state.chartInstance.destroy();
    }

    const dailyValues = result.daily_values || [];
    if (dailyValues.length === 0) return;

    const labels = dailyValues.map((d) => d.date);
    const costData = dailyValues.map((d) => d.cost);
    const valueData = dailyValues.map((d) => d.value);

    const ctx = document.getElementById("return-chart").getContext("2d");
    state.chartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "累计市值",
                    data: valueData,
                    borderColor: "#4f6ef7",
                    backgroundColor: "rgba(79,110,247,0.08)",
                    borderWidth: 2,
                    fill: true,
                    tension: 0.1,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                },
                {
                    label: "累计投入",
                    data: costData,
                    borderColor: "#aab2bd",
                    borderWidth: 1.5,
                    borderDash: [6, 3],
                    fill: false,
                    tension: 0.1,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: "index",
            },
            plugins: {
                legend: {
                    position: "top",
                    labels: {
                        usePointStyle: true,
                        padding: 20,
                    },
                },
                tooltip: {
                    callbacks: {
                        label: function (ctx) {
                            return `${ctx.dataset.label}: ¥${ctx.raw.toLocaleString()}`;
                        },
                    },
                },
            },
            scales: {
                x: {
                    display: true,
                    ticks: {
                        maxTicksLimit: 12,
                    },
                },
                y: {
                    ticks: {
                        callback: function (value) {
                            return "¥" + value.toLocaleString();
                        },
                    },
                },
            },
        },
    });
}

function renderCompareChart() {
    if (state.compareChartInstance) {
        state.compareChartInstance.destroy();
    }

    const results = Object.values(state.backtestResults);
    if (results.length === 0) return;

    // 找到所有结果的最长日期范围
    const allDates = new Set();
    results.forEach((r) => {
        (r.daily_values || []).forEach((d) => allDates.add(d.date));
    });
    const labels = Array.from(allDates).sort();

    const colors = ["#4f6ef7", "#27ae60", "#f39c12", "#e74c3c", "#9b59b6", "#1abc9c", "#e67e22", "#2c3e50"];

    const datasets = results.map((r, i) => {
        const valueMap = {};
        (r.daily_values || []).forEach((d) => {
            valueMap[d.date] = d.value;
        });
        const data = labels.map((d) => valueMap[d] || null);

        return {
            label: r.etf_name,
            data: data,
            borderColor: colors[i % colors.length],
            backgroundColor: "transparent",
            borderWidth: 2,
            tension: 0.1,
            pointRadius: 0,
            pointHoverRadius: 4,
            spanGaps: false,
        };
    });

    const ctx = document.getElementById("compare-chart").getContext("2d");
    state.compareChartInstance = new Chart(ctx, {
        type: "line",
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: "index" },
            plugins: {
                legend: { position: "top", labels: { usePointStyle: true, padding: 20 } },
                tooltip: {
                    callbacks: {
                        label: function (ctx) {
                            if (ctx.raw === null) return null;
                            return `${ctx.dataset.label}: ¥${ctx.raw.toLocaleString()}`;
                        },
                    },
                },
            },
            scales: {
                x: { ticks: { maxTicksLimit: 12 } },
                y: {
                    ticks: {
                        callback: function (v) {
                            return v >= 1000000 ? "¥" + (v / 1000000).toFixed(1) + "M" : "¥" + v.toLocaleString();
                        },
                    },
                },
            },
        },
    });
}

function renderCompareTable() {
    const results = Object.values(state.backtestResults);
    const tbody = document.querySelector("#compare-table tbody");
    tbody.innerHTML = "";

    let bestReturnRate = -Infinity;
    results.forEach((r) => {
        if (r.total_return_rate > bestReturnRate) bestReturnRate = r.total_return_rate;
    });

    results.forEach((r) => {
        const tr = document.createElement("tr");
        const isBest = r.total_return_rate === bestReturnRate && results.length > 1;
        if (isBest) tr.style.background = "#f0fdf4";
        tr.innerHTML = `
            <td>${isBest ? "🏆 " : ""}${r.etf_name}</td>
            <td>¥${r.total_invested.toLocaleString()}</td>
            <td>¥${r.final_value.toLocaleString()}</td>
            <td class="${r.total_return >= 0 ? "return-positive" : "return-negative"}">
                ¥${r.total_return.toLocaleString()}
            </td>
            <td class="${r.total_return_rate >= 0 ? "return-positive" : "return-negative"}">
                ${(r.total_return_rate * 100).toFixed(2)}%
            </td>
            <td>${(r.cagr * 100).toFixed(2)}%</td>
            <td>${(r.max_drawdown * 100).toFixed(2)}%</td>
            <td>${r.sharpe_ratio.toFixed(2)}</td>
            <td>${(r.xirr * 100).toFixed(2)}%</td>
        `;
        tbody.appendChild(tr);
    });

    // 多 ETF 时显示对比区域
    document.getElementById("compare-content").classList.toggle(
        "hidden",
        results.length <= 1
    );
}

// ===== 日志面板 =====
const logState = {
    open: false,
    eventSource: null,
    lastId: null,
    entries: [],
    errorCount: 0,
    warnCount: 0,
};

function initLogPanel() {
    const toggleBtn = document.getElementById("log-toggle-btn");
    const closeBtn = document.getElementById("log-close-btn");
    const clearBtn = document.getElementById("log-clear-btn");
    const overlay = document.getElementById("log-overlay");

    toggleBtn.addEventListener("click", toggleLogPanel);
    closeBtn.addEventListener("click", closeLogPanel);
    overlay.addEventListener("click", closeLogPanel);
    clearBtn.addEventListener("click", clearLogs);

    // 页面加载时立即建立 SSE 连接
    connectLogSSE();
}

function updateLogBadge() {
    const badge = document.getElementById("log-badge");
    const total = logState.errorCount + logState.warnCount;
    if (total > 0 && !logState.open) {
        badge.textContent = total > 99 ? "99+" : total;
        badge.classList.remove("hidden");
        if (logState.errorCount > 0) {
            badge.style.background = "var(--danger)";
        } else {
            badge.style.background = "var(--warning)";
        }
    } else {
        badge.classList.add("hidden");
    }
}

function toggleLogPanel() {
    if (logState.open) {
        closeLogPanel();
    } else {
        openLogPanel();
    }
}

function openLogPanel() {
    const panel = document.getElementById("log-panel");
    const overlay = document.getElementById("log-overlay");
    const toggleBtn = document.getElementById("log-toggle-btn");

    panel.classList.add("open");
    overlay.classList.remove("hidden");
    toggleBtn.classList.add("active");
    // 打开面板时清除角标
    logState.errorCount = 0;
    logState.warnCount = 0;
    updateLogBadge();
    logState.open = true;

    // 确保 SSE 连接
    if (!logState.eventSource || logState.eventSource.readyState === EventSource.CLOSED) {
        connectLogSSE();
    }

    scrollLogToBottom();
}

function closeLogPanel() {
    const panel = document.getElementById("log-panel");
    const overlay = document.getElementById("log-overlay");
    const toggleBtn = document.getElementById("log-toggle-btn");

    panel.classList.remove("open");
    overlay.classList.add("hidden");
    toggleBtn.classList.remove("active");
    logState.open = false;
}

function clearLogs() {
    logState.entries = [];
    logState.lastId = null;
    logState.errorCount = 0;
    logState.warnCount = 0;
    updateLogBadge();
    const container = document.getElementById("log-entries");
    container.innerHTML = '<div class="log-empty">日志已清空，等待新日志...</div>';
}

function connectLogSSE() {
    if (logState.eventSource) {
        logState.eventSource.close();
    }

    const es = new EventSource("/api/logs/stream");
    logState.eventSource = es;

    es.onmessage = function (event) {
        const text = event.data;
        const id = parseInt(event.lastEventId);
        if (!isNaN(id)) logState.lastId = id;

        const parsed = parseLogLine(text);

        // 统计错误和警告
        if (parsed.level === "ERROR") {
            logState.errorCount++;
            // 有新错误时闪烁按钮
            const btn = document.getElementById("log-toggle-btn");
            btn.classList.add("has-error");
            setTimeout(() => btn.classList.remove("has-error"), 2000);
        } else if (parsed.level === "WARNING") {
            logState.warnCount++;
        }

        logState.entries.push(parsed);
        appendLogEntry(parsed);
        updateLogBadge();
    };

    es.onerror = function () {
        // SSE 自动重连
    };
}

function parseLogLine(text) {
    // 格式: [HH:MM:SS] [LEVEL] [name] message
    const match = text.match(/^\[(\d{2}:\d{2}:\d{2})\]\s+\[(\w+)\]\s+\[([^\]]+)\]\s+(.*)$/);
    if (match) {
        return {
            time: match[1],
            level: match[2],
            name: match[3],
            message: match[4],
        };
    }
    // 无法解析的原始文本
    return {
        time: "",
        level: "DEBUG",
        name: "",
        message: text,
    };
}

function appendLogEntry(parsed) {
    const container = document.getElementById("log-entries");

    // 移除空状态提示
    const emptyEl = container.querySelector(".log-empty");
    if (emptyEl) emptyEl.remove();

    const el = document.createElement("div");
    el.className = `log-entry log-${parsed.level}`;

    const parts = [];
    if (parsed.time) parts.push(`<span class="log-time">${parsed.time}</span>`);
    parts.push(`<span class="log-level">[${parsed.level}]</span>`);
    if (parsed.name) parts.push(`<span class="log-name">[${parsed.name}]</span>`);
    parts.push(escapeHtml(parsed.message));

    el.innerHTML = parts.join(" ");
    container.appendChild(el);

    // 限制日志条目数量
    const maxEntries = 500;
    while (container.children.length > maxEntries) {
        container.removeChild(container.firstChild);
    }

    // 自动滚动（仅当面板打开且用户在底部附近时）
    if (logState.open) {
        const scrollBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
        if (scrollBottom < 60) {
            container.scrollTop = container.scrollHeight;
        }
    }
}

function scrollLogToBottom() {
    const container = document.getElementById("log-entries");
    setTimeout(() => {
        container.scrollTop = container.scrollHeight;
    }, 100);
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}
