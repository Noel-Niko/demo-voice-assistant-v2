"""Self-contained HTML dashboard template (no external dependencies)."""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Conversation Intelligence - Metrics Dashboard</title>
    <style>
        :root {
            --primary: #2563eb;
            --primary-light: #dbeafe;
            --success: #16a34a;
            --warning: #d97706;
            --danger: #dc2626;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --border: #e2e8f0;
            --text: #1e293b;
            --text-muted: #64748b;
            --radius: 8px;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: var(--bg);
            color: var(--text);
            padding: 1.5rem;
            max-width: 1400px;
            margin: 0 auto;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 2px solid var(--border);
        }
        header h1 { font-size: 1.5rem; font-weight: 700; }
        .header-actions { display: flex; align-items: center; gap: 1rem; }
        #refreshTime { font-size: 0.8rem; color: var(--text-muted); }
        .btn {
            padding: 0.5rem 1rem;
            border-radius: 6px;
            border: 1px solid var(--border);
            background: var(--card-bg);
            font-size: 0.8rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s;
        }
        .btn:hover { background: #f1f5f9; border-color: var(--primary); color: var(--primary); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-primary { background: var(--primary); color: white; border-color: var(--primary); }
        .btn-primary:hover { background: #1d4ed8; }
        #backfillStatus { font-size: 0.8rem; color: var(--text-muted); }
        #noData {
            text-align: center;
            padding: 4rem 2rem;
            color: var(--text-muted);
            font-size: 1.1rem;
        }

        /* KPI Cards */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .kpi-card {
            background: var(--card-bg);
            border-radius: var(--radius);
            padding: 1.25rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            border: 1px solid var(--border);
        }
        .kpi-value {
            font-size: 1.75rem;
            font-weight: 700;
            color: var(--primary);
            margin-bottom: 0.25rem;
        }
        .kpi-label { font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }

        /* Sections */
        .section {
            margin-bottom: 2rem;
            background: var(--card-bg);
            border-radius: var(--radius);
            padding: 1.25rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            border: 1px solid var(--border);
        }
        .section-title {
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border);
        }

        /* Table */
        .table-wrapper { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
        th {
            cursor: pointer;
            background: #f1f5f9;
            padding: 0.6rem 0.75rem;
            text-align: left;
            font-weight: 600;
            white-space: nowrap;
            user-select: none;
            border-bottom: 2px solid var(--border);
            position: relative;
            z-index: 1;
        }
        th:hover { background: #e2e8f0; }
        th .sort-arrow { font-size: 0.7rem; margin-left: 0.3rem; opacity: 0.4; }
        th.active .sort-arrow { opacity: 1; color: var(--primary); }
        td {
            padding: 0.5rem 0.75rem;
            border-bottom: 1px solid var(--border);
            white-space: nowrap;
        }
        tr:hover td { background: #f8fafc; }
        .badge {
            display: inline-block;
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge-yes { background: #dcfce7; color: #166534; }
        .badge-no { background: #fee2e2; color: #991b1b; }
        .badge-pending { background: #fef9c3; color: #854d0e; }

        /* Stats grid for sub-sections */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 1rem;
        }
        .stat-item { text-align: center; padding: 0.75rem; }
        .stat-value { font-size: 1.4rem; font-weight: 700; color: var(--text); }
        .stat-label { font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem; }

        /* Model breakdown bars */
        .model-row { display: flex; align-items: center; margin-bottom: 0.75rem; gap: 0.75rem; }
        .model-name { width: 140px; font-size: 0.85rem; font-weight: 500; flex-shrink: 0; }
        .model-bar-container { flex: 1; height: 24px; background: #f1f5f9; border-radius: 4px; overflow: hidden; }
        .model-bar { height: 100%; background: var(--primary); border-radius: 4px; transition: width 0.3s; }
        .model-stats { width: 280px; font-size: 0.8rem; color: var(--text-muted); flex-shrink: 0; }

        /* Tooltips */
        .info-icon {
            display: inline-block;
            width: 16px;
            height: 16px;
            line-height: 16px;
            text-align: center;
            border-radius: 50%;
            background: var(--primary-light);
            color: var(--primary);
            font-size: 0.7rem;
            font-weight: 700;
            cursor: help;
            margin-left: 0.4rem;
            position: relative;
        }
        .info-icon:hover::after {
            content: attr(data-tooltip);
            position: absolute;
            left: 50%;
            bottom: calc(100% + 8px);
            transform: translateX(-50%);
            background: var(--text);
            color: white;
            padding: 0.75rem 1rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 400;
            white-space: pre-line;
            width: 350px;
            text-align: left;
            z-index: 1000;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            max-width: 90vw;
            line-height: 1.5;
        }
        .info-icon:hover::before {
            content: '';
            position: absolute;
            left: 50%;
            bottom: calc(100% + 2px);
            transform: translateX(-50%);
            border: 6px solid transparent;
            border-top-color: var(--text);
            z-index: 1001;
        }

        /* Section group headers */
        .section-group-header {
            font-size: 1.3rem;
            font-weight: 700;
            color: var(--primary);
            margin: 2rem 0 1rem 0;
            padding: 0.75rem 1rem;
            background: linear-gradient(90deg, var(--primary-light) 0%, transparent 100%);
            border-left: 4px solid var(--primary);
        }
    </style>
</head>
<body>
    <header>
        <div style="display: flex; align-items: center; gap: 1rem;">
            <img src="data:image/png;base64,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"
                 alt="Conversation Intelligence"
                 style="height: 40px; width: auto;" />
            <h1>Conversation Intelligence Metrics</h1>
        </div>
        <div class="header-actions">
            <span id="backfillStatus"></span>
            <button id="backfillBtn" class="btn btn-primary" onclick="runBackfill()">Sync from DB</button>
            <span id="refreshTime">Loading...</span>
        </div>
    </header>
    <div id="noData" style="display:none;">
        No conversation data found. Complete a conversation in the main app to generate export data.
    </div>
    <div id="content" style="display:none;">
        <section class="kpi-grid" id="kpiCards"></section>

        <!-- CUSTOMER SERVICE METRICS -->
        <h2 class="section-group-header">Customer Service Metrics</h2>

        <section class="section" id="acwSection">
            <h2 class="section-title">
                End-of-Call Form (ACW)
                <span class="info-icon" data-tooltip="After-Call Work metrics from the end-of-call form: (1) Notes Completion = % of conversations with wrap-up notes filled out, (2) Agent Feedback = Agent's rating of overall AI helpfulness (Up/Down/None), (3) CRM Auto-Fill = % of CRM fields populated by AI vs manually, (4) Disposition = Call outcome codes selected by agents.">ℹ</span>
            </h2>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:2rem;">
                <div>
                    <h3 style="font-size: 0.9rem; font-weight: 600; margin-bottom: 0.75rem;">Disposition Distribution</h3>
                    <div id="dispositionBreakdown"></div>
                </div>
                <div class="stats-grid" id="acwStatsGrid"></div>
            </div>
        </section>

        <section class="section" id="manualSearchSection">
            <h2 class="section-title">
                Manual Search Activity
                <span class="info-icon" data-tooltip="Manual queries entered by agents when listening mode is OFF. Shows proactive AI usage outside automated suggestions.">ℹ</span>
            </h2>
            <div class="stats-grid" id="manualSearchMetrics"></div>
        </section>

        <section class="section">
            <h2 class="section-title">
                Conversations
                <span class="info-icon" data-tooltip="Detailed per-conversation metrics. Click column headers to sort.

Column Definitions:
• ID - Unique identifier (truncated)
• Status - Active/completed
• Duration - Transcript length (mm:ss)
• Disposition - Agent-selected outcome code
• FCR - First Call Resolution (Yes if resolved)
• AI Cost - Total LLM costs (USD)
• AI Calls - Number of LLM API calls
• Manual Q - Agent-initiated AI queries
• Auto Q - Automated listening mode queries
• Summaries - Real-time summaries generated
• Edits - Agent edits to AI content">ℹ</span>
                <span id="conversationCount" style="font-weight:normal; font-size:0.9rem; color:var(--text-muted); margin-left:0.5rem;"></span>
            </h2>
            <div class="table-wrapper">
                <table id="conversationsTable">
                    <thead><tr>
                        <th data-sort="conversation_id">ID <span class="sort-arrow">&#9650;</span></th>
                        <th data-sort="status">Status <span class="sort-arrow">&#9650;</span></th>
                        <th data-sort="duration_secs">Duration <span class="sort-arrow">&#9650;</span></th>
                        <th data-sort="disposition_code">Disposition <span class="sort-arrow">&#9650;</span></th>
                        <th data-sort="fcr">FCR <span class="sort-arrow">&#9650;</span></th>
                        <th data-sort="total_ai_cost_usd">AI Cost <span class="sort-arrow">&#9650;</span></th>
                        <th data-sort="ai_call_count">AI Calls <span class="sort-arrow">&#9650;</span></th>
                        <th data-sort="manual_query_count">Manual Q <span class="sort-arrow">&#9650;</span></th>
                        <th data-sort="auto_query_count">Auto Q <span class="sort-arrow">&#9650;</span></th>
                        <th data-sort="summary_count">Summaries <span class="sort-arrow">&#9650;</span></th>
                        <th data-sort="total_edits">Edits <span class="sort-arrow">&#9650;</span></th>
                    </tr></thead>
                    <tbody id="tableBody"></tbody>
                </table>
            </div>
            <div style="text-align:center; margin-top:1rem;">
                <button id="toggleTableBtn" class="btn" onclick="toggleTableExpand()" style="display:none;">Show More</button>
            </div>
        </section>

        <!-- AI PERFORMANCE METRICS -->
        <h2 class="section-group-header">AI Performance Metrics</h2>

        <section class="section" id="modelSection" style="display:none;">
            <h2 class="section-title">
                AI Cost by Model
                <span class="info-icon" data-tooltip="LLM usage breakdown by model showing call count, tokens consumed, total cost, and latency percentiles (p50=median, p99=99th percentile).">ℹ</span>
            </h2>
            <div id="modelBreakdown"></div>
        </section>

        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:1rem;">
            <section class="section" id="complianceSection">
                <h2 class="section-title">
                    Compliance Detection
                    <span class="info-icon" data-tooltip="AI accuracy detecting compliance requirements. Override rate shows how often agents corrected AI predictions.">ℹ</span>
                </h2>
                <div class="stats-grid" id="complianceMetrics"></div>
            </section>
            <section class="section" id="listeningSection">
                <h2 class="section-title">
                    Listening Mode
                    <span class="info-icon" data-tooltip="Automated suggestion sessions where AI proactively detects opportunities and triggers queries based on conversation context.">ℹ</span>
                </h2>
                <div class="stats-grid" id="listeningMetrics"></div>
            </section>
            <section class="section" id="summarySection">
                <h2 class="section-title">
                    AI Summaries
                    <span class="info-icon" data-tooltip="Real-time summaries generated during conversations. Edit count shows agent refinements to AI-generated text.">ℹ</span>
                </h2>
                <div class="stats-grid" id="summaryMetrics"></div>
            </section>
        </div>

        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:1rem;">
            <section class="section" id="feedbackSection">
                <h2 class="section-title">
                    AI Feedback
                    <span class="info-icon" data-tooltip="Thumbs up/down ratings on INDIVIDUAL AI suggestions during conversations (not the same as overall AI helpfulness rating in ACW form). Shows agent satisfaction with specific suggestions. Approval rate = rated_up / (rated_up + rated_down) × 100.">ℹ</span>
                </h2>
                <div class="stats-grid" id="feedbackMetrics"></div>
            </section>
            <section class="section" id="aiSuggestionSection">
                <h2 class="section-title">
                    AI Suggestion Usage
                    <span class="info-icon" data-tooltip="How often agents interact with AI features including manual queries, auto queries, ratings, and mode switches.">ℹ</span>
                </h2>
                <div class="stats-grid" id="aiSuggestionMetrics"></div>
            </section>
        </div>
    </div>

    <script>
        let currentSort = { column: 'conversation_id', direction: 'asc' };
        let currentConversations = [];
        let mainAppUrl = 'http://localhost:8765';
        let tableExpanded = false;

        async function runBackfill() {
            var btn = document.getElementById('backfillBtn');
            var status = document.getElementById('backfillStatus');
            btn.disabled = true;
            btn.textContent = 'Syncing...';
            status.textContent = '';
            try {
                var resp = await fetch(mainAppUrl + '/api/dashboard/backfill', { method: 'POST' });
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                var result = await resp.json();
                status.textContent = 'Exported ' + result.exported + '/' + result.total_conversations + ' conversations';
                status.style.color = 'var(--success)';
                // Reload dashboard data immediately
                await loadDashboard();
            } catch (e) {
                status.textContent = 'Failed: ' + e.message + ' (is the main app running on ' + mainAppUrl + '?)';
                status.style.color = 'var(--danger)';
            } finally {
                btn.disabled = false;
                btn.textContent = 'Sync from DB';
            }
        }

        function formatDuration(secs) {
            if (secs == null) return '-';
            const m = Math.floor(secs / 60);
            const s = Math.round(secs % 60);
            return m + 'm ' + s + 's';
        }
        function formatCurrency(usd) { return '$' + (usd || 0).toFixed(4); }
        function formatPct(pct) { return (pct || 0).toFixed(1) + '%'; }
        function shortId(id) { return id ? id.substring(0, 8) + '...' : '-'; }

        function renderKPIs(kpis) {
            const cards = [
                { value: kpis.total_conversations, label: 'Total Conversations' },
                { value: formatDuration(kpis.avg_duration_secs), label: 'Avg Duration' },
                { value: formatPct(kpis.avg_acw_pct), label: 'Avg ACW %' },
                { value: formatCurrency(kpis.total_ai_cost_usd), label: 'Total AI Cost' },
                { value: formatPct(kpis.fcr_rate), label: 'FCR Rate (' + kpis.fcr_resolved_count + '/' + kpis.fcr_eligible_count + ')' },
            ];
            document.getElementById('kpiCards').innerHTML = cards.map(function(c) {
                return '<div class="kpi-card"><div class="kpi-value">' + c.value + '</div><div class="kpi-label">' + c.label + '</div></div>';
            }).join('');
        }

        function toggleTableExpand() {
            tableExpanded = !tableExpanded;
            renderTable(currentConversations);
        }

        function renderTable(conversations) {
            var sorted = conversations.slice().sort(function(a, b) {
                var va = a[currentSort.column], vb = b[currentSort.column];
                if (va == null) va = '';
                if (vb == null) vb = '';
                if (typeof va === 'number' && typeof vb === 'number') {
                    return currentSort.direction === 'asc' ? va - vb : vb - va;
                }
                va = String(va); vb = String(vb);
                return currentSort.direction === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
            });

            // Limit to 5 rows if not expanded
            var displayRows = tableExpanded ? sorted : sorted.slice(0, 5);
            var toggleBtn = document.getElementById('toggleTableBtn');
            var countSpan = document.getElementById('conversationCount');

            if (sorted.length > 5) {
                toggleBtn.style.display = '';
                toggleBtn.textContent = tableExpanded ? 'Show Less' : 'Show More (' + (sorted.length - 5) + ' hidden)';
                countSpan.textContent = tableExpanded ? '(showing all ' + sorted.length + ')' : '(showing 5 of ' + sorted.length + ')';
            } else {
                toggleBtn.style.display = 'none';
                countSpan.textContent = sorted.length > 0 ? '(' + sorted.length + ')' : '';
            }

            document.getElementById('tableBody').innerHTML = displayRows.map(function(c) {
                var fcrBadge = c.fcr === true ? '<span class="badge badge-yes">Yes</span>'
                    : c.fcr === false ? '<span class="badge badge-no">No</span>'
                    : '<span class="badge badge-pending">-</span>';
                return '<tr>' +
                    '<td title="' + c.conversation_id + '">' + shortId(c.conversation_id) + '</td>' +
                    '<td>' + c.status + '</td>' +
                    '<td>' + formatDuration(c.duration_secs) + '</td>' +
                    '<td>' + (c.disposition_code || '-') + '</td>' +
                    '<td>' + fcrBadge + '</td>' +
                    '<td>' + formatCurrency(c.total_ai_cost_usd) + '</td>' +
                    '<td>' + c.ai_call_count + '</td>' +
                    '<td>' + c.manual_query_count + '</td>' +
                    '<td>' + c.auto_query_count + '</td>' +
                    '<td>' + c.summary_count + '</td>' +
                    '<td>' + c.total_edits + '</td>' +
                '</tr>';
            }).join('');

            // Update sort arrow styling
            document.querySelectorAll('th[data-sort]').forEach(function(th) {
                th.classList.remove('active');
                var arrow = th.querySelector('.sort-arrow');
                arrow.innerHTML = '&#9650;';
                if (th.dataset.sort === currentSort.column) {
                    th.classList.add('active');
                    arrow.innerHTML = currentSort.direction === 'asc' ? '&#9650;' : '&#9660;';
                }
            });
        }

        function getLatencyColor(latencyMs) {
            if (latencyMs < 500) return '#10b981'; // green
            if (latencyMs < 1000) return '#f59e0b'; // yellow
            return '#ef4444'; // red
        }

        function renderModelBreakdown(models) {
            var section = document.getElementById('modelSection');
            if (!models || models.length === 0) { section.style.display = 'none'; return; }
            section.style.display = '';
            var maxCost = Math.max.apply(null, models.map(function(m) { return m.total_cost_usd; })) || 1;
            document.getElementById('modelBreakdown').innerHTML = models.map(function(m) {
                var pct = (m.total_cost_usd / maxCost * 100).toFixed(0);
                var p99Color = getLatencyColor(m.p99_latency_ms);
                var p50Color = getLatencyColor(m.p50_latency_ms);
                return '<div class="model-row">' +
                    '<span class="model-name">' + m.model_name + '</span>' +
                    '<div class="model-bar-container"><div class="model-bar" style="width:' + pct + '%"></div></div>' +
                    '<span class="model-stats">' + m.call_count + ' calls | ' +
                        m.total_tokens.toLocaleString() + ' tokens | ' +
                        formatCurrency(m.total_cost_usd) + ' | ' +
                        '<span style="color:' + p50Color + '; font-weight: 600;" title="Median latency">' +
                        m.p50_latency_ms + 'ms p50</span> / ' +
                        '<span style="color:' + p99Color + '; font-weight: 600;" title="99th percentile latency">' +
                        m.p99_latency_ms + 'ms p99</span></span>' +
                '</div>';
            }).join('');
        }

        function renderStat(value, label) {
            return '<div class="stat-item"><div class="stat-value">' + value + '</div><div class="stat-label">' + label + '</div></div>';
        }

        function renderCompliance(c) {
            var el = document.getElementById('complianceMetrics');
            if (c.total_attempts === 0) {
                el.innerHTML = '<div class="stat-item"><div class="stat-label">No compliance data</div></div>';
                return;
            }
            el.innerHTML =
                renderStat(c.total_attempts, 'Total Checks') +
                renderStat(c.ai_correct, 'AI Correct') +
                renderStat(c.agent_overrides, 'Agent Overrides') +
                renderStat(formatPct(c.override_rate * 100), 'Override Rate') +
                renderStat((c.avg_confidence * 100).toFixed(0) + '%', 'Avg AI Confidence');
        }

        function renderListeningMode(lm) {
            var el = document.getElementById('listeningMetrics');
            if (lm.total_sessions === 0) {
                el.innerHTML = '<div class="stat-item"><div class="stat-label">No listening mode data</div></div>';
                return;
            }
            el.innerHTML =
                renderStat(lm.total_sessions, 'Sessions') +
                renderStat(formatDuration(lm.total_duration_secs), 'Total Duration') +
                renderStat(lm.total_auto_queries, 'Auto Queries') +
                renderStat(lm.avg_queries_per_session.toFixed(1), 'Avg Q/Session') +
                renderStat(lm.total_opportunities, 'Opportunities');
        }

        function renderSummaryMetrics(sm) {
            var el = document.getElementById('summaryMetrics');
            el.innerHTML =
                renderStat(sm.total_summaries, 'Total Generated') +
                renderStat(sm.total_edits, 'Agent Edits') +
                renderStat(sm.avg_summaries_per_conversation.toFixed(1), 'Avg/Conversation');
        }

        function renderFeedbackMetrics(fm) {
            var el = document.getElementById('feedbackMetrics');
            if (fm.total_rated === 0) {
                el.innerHTML = '<div class="stat-item"><div class="stat-label">No feedback data</div></div>';
                return;
            }
            el.innerHTML =
                renderStat(fm.total_rated_up, 'Thumbs Up') +
                renderStat(fm.total_rated_down, 'Thumbs Down') +
                renderStat(fm.total_rated, 'Total Rated') +
                renderStat(formatPct(fm.approval_rate), 'Approval Rate');
        }

        function renderACWMetrics(acw) {
            var dispEl = document.getElementById('dispositionBreakdown');
            var statsEl = document.getElementById('acwStatsGrid');
            var section = document.getElementById('acwSection');

            if (acw.total_with_disposition === 0 && acw.crm_total_extractions === 0) {
                section.style.display = 'none';
                return;
            }
            section.style.display = '';

            // Disposition distribution as horizontal bars
            var dispKeys = Object.keys(acw.disposition_distribution);
            if (dispKeys.length > 0) {
                var maxCount = Math.max.apply(null, dispKeys.map(function(k) { return acw.disposition_distribution[k]; })) || 1;
                dispEl.innerHTML = dispKeys.map(function(code) {
                    var count = acw.disposition_distribution[code];
                    var pct = (count / maxCount * 100).toFixed(0);
                    return '<div class="model-row">' +
                        '<span class="model-name" style="width:180px;">' + code + '</span>' +
                        '<div class="model-bar-container"><div class="model-bar" style="width:' + pct + '%"></div></div>' +
                        '<span class="model-stats" style="width:60px;">' + count + '</span>' +
                    '</div>';
                }).join('');
            } else {
                dispEl.innerHTML = '<div class="stat-label">No disposition data</div>';
            }

            // ACW stats
            statsEl.innerHTML =
                renderStat(formatPct(acw.notes_completion_rate), 'Notes Completion') +
                renderStat(acw.agent_feedback_up + ' / ' + acw.agent_feedback_down + ' / ' + acw.agent_feedback_none, 'Agent Feedback (Up/Down/None)') +
                renderStat(formatPct(acw.crm_auto_fill_rate), 'CRM Auto-Fill Rate') +
                renderStat(acw.crm_ai_extractions + ' / ' + acw.crm_total_extractions, 'AI Extractions / Total');
        }

        function renderAISuggestionMetrics(ai) {
            var el = document.getElementById('aiSuggestionMetrics');
            if (ai.total_interactions === 0) {
                el.innerHTML = '<div class="stat-item"><div class="stat-label">No AI suggestion data</div></div>';
                return;
            }
            el.innerHTML =
                renderStat(ai.total_interactions, 'Total Interactions') +
                renderStat(ai.total_manual_queries, 'Manual Queries') +
                renderStat(ai.total_auto_queries, 'Auto Queries') +
                renderStat(ai.total_suggestions_rated, 'Suggestions Rated') +
                renderStat(ai.avg_queries_per_conversation.toFixed(1), 'Avg Queries/Conv') +
                renderStat(formatPct(ai.query_usage_rate), 'Query Usage Rate');
        }

        function renderManualSearchMetrics(ms) {
            var el = document.getElementById('manualSearchMetrics');
            if (ms.total_manual_queries === 0) {
                el.innerHTML = '<div class="stat-item"><div class="stat-label">No manual search data</div></div>';
                return;
            }
            el.innerHTML =
                renderStat(ms.total_manual_queries, 'Total Manual Queries') +
                renderStat(ms.total_manual_outside_listening, 'Outside Listening') +
                renderStat(ms.total_manual_inside_listening, 'Inside Listening') +
                renderStat(formatPct(ms.outside_query_rate), 'Outside Rate') +
                renderStat(ms.avg_outside_per_conversation.toFixed(1), 'Avg Outside/Conv') +
                renderStat(ms.conversations_with_outside_queries, 'Convs w/ Outside');
        }

        async function loadDashboard() {
            try {
                var resp = await fetch('/api/dashboard/data');
                var data = await resp.json();

                if (data.main_app_url) mainAppUrl = data.main_app_url;

                if (data.kpis.total_conversations === 0) {
                    document.getElementById('noData').style.display = '';
                    document.getElementById('content').style.display = 'none';
                } else {
                    document.getElementById('noData').style.display = 'none';
                    document.getElementById('content').style.display = '';
                }

                currentConversations = data.conversations;
                renderKPIs(data.kpis);
                renderTable(data.conversations);
                renderModelBreakdown(data.model_breakdown);
                renderCompliance(data.compliance);
                renderListeningMode(data.listening_mode);
                renderSummaryMetrics(data.summary_metrics);
                renderFeedbackMetrics(data.feedback_metrics);
                renderACWMetrics(data.acw_metrics);
                renderAISuggestionMetrics(data.ai_suggestion_metrics);
                renderManualSearchMetrics(data.manual_search_metrics);
                document.getElementById('refreshTime').textContent = 'Updated: ' + new Date().toLocaleTimeString();
            } catch (e) {
                document.getElementById('refreshTime').textContent = 'Error loading data: ' + e.message;
            }
        }

        // Sort click handlers
        document.querySelectorAll('th[data-sort]').forEach(function(th) {
            th.addEventListener('click', function() {
                var col = this.dataset.sort;
                if (currentSort.column === col) {
                    currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
                } else {
                    currentSort.column = col;
                    currentSort.direction = 'asc';
                }
                renderTable(currentConversations);
            });
        });

        // Initial load + auto-refresh every 30s
        loadDashboard();
        setInterval(loadDashboard, 30000);
    </script>
</body>
</html>
"""
