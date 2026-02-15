import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import {
    AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
    ResponsiveContainer, BarChart, Bar, Cell
} from 'recharts';

/* ── API Helpers ──────────────────────────────────────── */

const API_BASE = '/api';

async function apiGet(path) {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
}

async function apiPost(path, body) {
    const res = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
}

/* ── Suggested Queries ───────────────────────────────── */

const SUGGESTED_QUERIES = [
    {
        label: 'Full Safety Scan',
        icon: '🔍',
        query: 'Scan for any emerging drug safety signals in the FAERS database from the last 90 days. Look for drugs with unusual spikes in adverse event reporting, particularly for serious reactions like cardiac events, hepatotoxicity, and rhabdomyolysis.',
    },
    {
        label: 'Cardiac Signals',
        icon: '❤️',
        query: 'Investigate cardiac-related adverse events in the FAERS database. Look for drugs associated with arrhythmia, cardiac arrest, QT prolongation, and myocardial infarction with elevated PRR scores.',
    },
    {
        label: 'Hepatotoxicity Check',
        icon: '🫁',
        query: 'Scan for hepatotoxicity signals. Identify drugs showing disproportionate reporting of liver injury, hepatic failure, jaundice, and elevated liver enzymes in recent FAERS submissions.',
    },
    {
        label: 'Drug Interactions',
        icon: '💊',
        query: 'Analyze potential drug-drug interactions in FAERS data. Look for cases where concomitant drug usage correlates with increased serious adverse events, particularly fatal or life-threatening outcomes.',
    },
    {
        label: 'Pediatric Safety',
        icon: '👶',
        query: 'Scan for adverse event signals in pediatric populations (age 0-17). Identify drugs with unusual adverse event patterns in children, focusing on developmental and neurological reactions.',
    },
    {
        label: 'Rhabdomyolysis',
        icon: '🦴',
        query: 'Investigate rhabdomyolysis signals across all drugs. Identify medications with elevated PRR for muscle-related adverse events including rhabdomyolysis, myalgia, and elevated CK levels.',
    },
];

/* ── Components ──────────────────────────────────────── */

function KPICard({ label, value, colorClass, detail }) {
    return (
        <div className="kpi-card animate-in">
            <div className="kpi-label">{label}</div>
            <div className={`kpi-value ${colorClass}`}>{value}</div>
            {detail && <div className="kpi-detail">{detail}</div>}
        </div>
    );
}

function PriorityBadge({ priority }) {
    const p = (priority || 'medium').toLowerCase();
    return (
        <span className={`priority-badge ${p}`}>
            {p === 'critical' && '⚠ '}
            {p === 'high' && '▲ '}
            {p}
        </span>
    );
}

function RiskIndicator({ level }) {
    const l = (level || 'moderate').toLowerCase();
    return (
        <span className={`risk-indicator ${l}`}>
            {l === 'critical' ? '🔴' : l === 'high' ? '🟠' : l === 'moderate' ? '🟡' : '🟢'}
            {' '}{level || 'UNKNOWN'}
        </span>
    );
}

function PipelineSteps({ currentAgent, status }) {
    const steps = [
        { id: 'signal_scanner', icon: '🔍', name: 'Signal Scanner', desc: 'Detecting anomalies' },
        { id: 'case_investigator', icon: '🔬', name: 'Case Investigator', desc: 'Analyzing patterns' },
        { id: 'safety_reporter', icon: '📋', name: 'Safety Reporter', desc: 'Generating reports' },
    ];

    const getStepState = (stepId) => {
        if (status === 'complete') return 'completed';
        const stepIndex = steps.findIndex(s => s.id === stepId);
        const currentIndex = steps.findIndex(s => s.id === currentAgent);
        if (currentIndex === -1) return '';
        if (stepIndex < currentIndex) return 'completed';
        if (stepIndex === currentIndex) return 'active';
        return '';
    };

    return (
        <div className="pipeline-steps">
            {steps.map(step => {
                const state = getStepState(step.id);
                return (
                    <div key={step.id} className={`pipeline-step ${state}`}>
                        <div className="step-icon">{step.icon}</div>
                        <div className="step-name">{step.name}</div>
                        <div className={`step-status ${state}`}>
                            {state === 'active' && <><span className="spinner" /> Running...</>}
                            {state === 'completed' && '✓ Complete'}
                            {state === '' && 'Waiting'}
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

function SignalTable({ signals, onSelectSignal }) {
    if (!signals || signals.length === 0) {
        return (
            <div className="empty-state">
                <div className="empty-state-icon">🔍</div>
                <div className="empty-state-text">No signals detected yet. Run an investigation to scan for drug safety signals.</div>
            </div>
        );
    }

    return (
        <table className="signal-table">
            <thead>
                <tr>
                    <th>Drug</th>
                    <th>Reaction</th>
                    <th>PRR</th>
                    <th>Cases</th>
                    <th>Spike</th>
                    <th>Priority</th>
                </tr>
            </thead>
            <tbody>
                {signals.map((signal, i) => (
                    <tr key={i} onClick={() => onSelectSignal && onSelectSignal(signal)} style={{ cursor: 'pointer' }}>
                        <td>
                            <div className="signal-drug">{signal.drug_name}</div>
                        </td>
                        <td className="signal-reaction">{signal.reaction_term}</td>
                        <td>
                            <span className={`prr-value ${signal.prr > 3 ? 'high' : signal.prr > 2 ? 'medium' : 'low'}`}>
                                {typeof signal.prr === 'number' ? signal.prr.toFixed(2) : signal.prr}
                            </span>
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                            {signal.case_count}
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', color: signal.spike_ratio > 2 ? 'var(--accent-red)' : 'var(--text-secondary)' }}>
                            {typeof signal.spike_ratio === 'number' ? `${signal.spike_ratio.toFixed(1)}x` : signal.spike_ratio}
                        </td>
                        <td><PriorityBadge priority={signal.priority} /></td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

function ReportViewer({ reports }) {
    const [activeTab, setActiveTab] = useState(0);

    if (!reports || reports.length === 0) {
        return (
            <div className="empty-state">
                <div className="empty-state-icon">📋</div>
                <div className="empty-state-text">No reports generated yet. Safety reports will appear here after an investigation completes.</div>
            </div>
        );
    }

    const report = reports[activeTab];

    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
                <div className="report-tabs">
                    {reports.map((r, i) => (
                        <button
                            key={i}
                            className={`report-tab ${i === activeTab ? 'active' : ''}`}
                            onClick={() => setActiveTab(i)}
                        >
                            {r.drug_name} → {r.reaction_term}
                        </button>
                    ))}
                </div>
                <RiskIndicator level={report.risk_level} />
            </div>
            <div className="report-content">
                <ReactMarkdown>{report.report_markdown || 'Report content unavailable.'}</ReactMarkdown>
            </div>
        </div>
    );
}

function ProgressLog({ messages }) {
    const logRef = useRef(null);

    useEffect(() => {
        if (logRef.current) {
            logRef.current.scrollTop = logRef.current.scrollHeight;
        }
    }, [messages]);

    if (!messages || messages.length === 0) return null;

    return (
        <div className="progress-log" ref={logRef}>
            {messages.map((msg, i) => (
                <div key={i} className="progress-entry">
                    <span className="timestamp">[{String(i + 1).padStart(2, '0')}]</span>
                    <span className="message">{msg}</span>
                </div>
            ))}
        </div>
    );
}

function SignalChart({ signals }) {
    if (!signals || signals.length === 0) return null;

    const data = signals.map(s => ({
        name: s.drug_name,
        prr: s.prr || 0,
        cases: s.case_count || 0,
        spike: s.spike_ratio || 0,
    }));

    const COLORS = ['#ef4444', '#f97316', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6'];

    return (
        <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(59,130,246,0.1)" />
                    <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <RechartsTooltip
                        contentStyle={{
                            background: '#1a2332',
                            border: '1px solid rgba(59,130,246,0.2)',
                            borderRadius: 8,
                            color: '#f1f5f9',
                            fontSize: 13,
                        }}
                    />
                    <Bar dataKey="prr" name="PRR Score" radius={[6, 6, 0, 0]}>
                        {data.map((_, i) => (
                            <Cell key={i} fill={COLORS[i % COLORS.length]} />
                        ))}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
        </div>
    );
}

/* ── Agent Reasoning Panel (NEW — Gap #1) ────────────── */

function ReasoningStep({ step, index }) {
    const [expanded, setExpanded] = useState(step.step_type === 'tool_call');

    const agentLabels = {
        signal_scanner: { name: 'Signal Scanner', icon: '🔍', color: 'var(--accent-blue)' },
        case_investigator: { name: 'Case Investigator', icon: '🔬', color: 'var(--accent-orange)' },
        safety_reporter: { name: 'Safety Reporter', icon: '📋', color: 'var(--accent-violet)' },
        system: { name: 'System', icon: '⚙️', color: 'var(--text-muted)' },
    };

    const agent = agentLabels[step.agent] || agentLabels.system;

    const stepIcons = {
        thinking: '💭',
        tool_call: '🔧',
        tool_result: '📊',
        conclusion: '✅',
    };

    const stepColors = {
        thinking: 'reasoning-thinking',
        tool_call: 'reasoning-tool-call',
        tool_result: 'reasoning-tool-result',
        conclusion: 'reasoning-conclusion',
    };

    return (
        <div
            className={`reasoning-step ${stepColors[step.step_type] || ''} animate-in`}
            style={{ animationDelay: `${index * 60}ms` }}
            onClick={() => step.step_type === 'tool_call' && setExpanded(!expanded)}
        >
            <div className="reasoning-step-header">
                <span className="reasoning-step-icon">{stepIcons[step.step_type] || '•'}</span>
                <span className="reasoning-step-type">{step.step_type?.toUpperCase()}</span>
                <span className="reasoning-step-agent" style={{ color: agent.color }}>
                    {agent.icon} {agent.name}
                </span>
            </div>
            <div className="reasoning-step-content">{step.content}</div>

            {/* Tool call details — expandable */}
            {step.step_type === 'tool_call' && step.tool_name && (
                <div className={`reasoning-tool-details ${expanded ? 'expanded' : ''}`}>
                    <div className="reasoning-tool-name">
                        <span className="tool-label">Tool:</span> {step.tool_name}
                    </div>
                    {step.tool_input && Object.keys(step.tool_input).length > 0 && (
                        <div className="reasoning-tool-input">
                            <span className="tool-label">Input:</span>
                            <code>{JSON.stringify(step.tool_input, null, 2)}</code>
                        </div>
                    )}
                    {step.tool_query && (
                        <div className="reasoning-esql-query">
                            <span className="tool-label">ES|QL:</span>
                            <pre className="esql-code">{step.tool_query}</pre>
                        </div>
                    )}
                </div>
            )}

            {/* Tool result data */}
            {step.step_type === 'tool_result' && step.tool_result && (
                <div className="reasoning-tool-result-data">
                    <code>{step.tool_result}</code>
                </div>
            )}
        </div>
    );
}

function AgentReasoningPanel({ reasoningTrace, isRunning }) {
    const panelRef = useRef(null);
    const [isCollapsed, setIsCollapsed] = useState(false);

    useEffect(() => {
        if (panelRef.current && !isCollapsed) {
            panelRef.current.scrollTop = panelRef.current.scrollHeight;
        }
    }, [reasoningTrace, isCollapsed]);

    // Group steps by agent
    const agentGroups = {};
    (reasoningTrace || []).forEach(step => {
        const key = step.agent || 'system';
        if (!agentGroups[key]) agentGroups[key] = [];
        agentGroups[key].push(step);
    });

    const stepCount = (reasoningTrace || []).length;
    const toolCallCount = (reasoningTrace || []).filter(s => s.step_type === 'tool_call').length;

    if (!reasoningTrace || reasoningTrace.length === 0) {
        return (
            <div className="empty-state" style={{ padding: '20px' }}>
                <div className="empty-state-icon">🧠</div>
                <div className="empty-state-text">
                    Agent reasoning will appear here in real-time as agents think, select tools, run ES|QL queries, and draw conclusions.
                </div>
            </div>
        );
    }

    return (
        <div className="reasoning-panel">
            <div className="reasoning-panel-toolbar">
                <div className="reasoning-panel-stats">
                    <span className="reasoning-stat">
                        <span className="reasoning-stat-value">{stepCount}</span> steps
                    </span>
                    <span className="reasoning-stat">
                        <span className="reasoning-stat-value">{toolCallCount}</span> tool calls
                    </span>
                    {isRunning && <span className="spinner" style={{ marginLeft: 8 }} />}
                </div>
                <button
                    className="reasoning-toggle-btn"
                    onClick={() => setIsCollapsed(!isCollapsed)}
                >
                    {isCollapsed ? '▼ Expand' : '▲ Collapse'}
                </button>
            </div>
            {!isCollapsed && (
                <div className="reasoning-steps-container" ref={panelRef}>
                    {(reasoningTrace || []).map((step, i) => (
                        <ReasoningStep key={i} step={step} index={i} />
                    ))}
                </div>
            )}
        </div>
    );
}

/* ── Query Suggestions (NEW — Gap #2) ────────────────── */

function QuerySuggestions({ onSelect, disabled }) {
    return (
        <div className="query-suggestions">
            <div className="query-suggestions-label">Quick queries:</div>
            <div className="query-suggestions-chips">
                {SUGGESTED_QUERIES.map((sq, i) => (
                    <button
                        key={i}
                        className="query-chip"
                        onClick={() => onSelect(sq.query)}
                        disabled={disabled}
                        title={sq.query}
                    >
                        <span className="query-chip-icon">{sq.icon}</span>
                        {sq.label}
                    </button>
                ))}
            </div>
        </div>
    );
}

/* ── Main App ────────────────────────────────────────── */

export default function App() {
    const [health, setHealth] = useState(null);
    const [investigation, setInvestigation] = useState(null);
    const [signals, setSignals] = useState([]);
    const [reports, setReports] = useState([]);
    const [progressMessages, setProgressMessages] = useState([]);
    const [reasoningTrace, setReasoningTrace] = useState([]);
    const [isRunning, setIsRunning] = useState(false);
    const [query, setQuery] = useState('');
    const [currentAgent, setCurrentAgent] = useState('');
    const [status, setStatus] = useState('idle');
    const [showReasoning, setShowReasoning] = useState(true);
    const wsRef = useRef(null);

    // Health check
    useEffect(() => {
        apiGet('/health')
            .then(setHealth)
            .catch(() => setHealth({ status: 'error' }));
    }, []);

    // WebSocket connection for real-time progress
    const connectWebSocket = useCallback((investigationId) => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/progress/${investigationId}`;

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'progress') {
                    const data = msg.data;

                    // Handle reasoning trace events
                    if (data.type === 'reasoning' && data.steps) {
                        setReasoningTrace(prev => [...prev, ...data.steps]);
                        return;
                    }

                    setProgressMessages(prev => [...prev, ...(data.progress || [])]);
                    if (data.status) setStatus(data.status);
                    if (data.node === 'scan_signals') setCurrentAgent('case_investigator');
                    if (data.node === 'investigate_cases') setCurrentAgent('safety_reporter');
                    if (data.node === 'generate_reports') setCurrentAgent('none');
                    if (data.node === 'compile_results') {
                        setStatus('complete');
                        setCurrentAgent('none');
                        setIsRunning(false);
                        // Refresh data
                        loadInvestigationData(investigationId);
                    }
                    if (data.node === 'error') {
                        setStatus('error');
                        setIsRunning(false);
                    }
                }
                if (msg.type === 'current_state') {
                    const data = msg.data;
                    setProgressMessages(data.progress || []);
                    setReasoningTrace(data.reasoning_trace || []);
                    setStatus(data.status);
                }
            } catch (e) {
                console.error('WebSocket parse error:', e);
            }
        };

        ws.onerror = () => console.error('WebSocket error');
        ws.onclose = () => console.log('WebSocket closed');
    }, []);

    const loadInvestigationData = async (investigationId) => {
        try {
            const inv = await apiGet(`/investigations/${investigationId}`);
            setInvestigation(inv);
            setSignals(inv.signals || []);
            setReports(inv.reports || []);
            setReasoningTrace(inv.reasoning_trace || []);
        } catch (e) {
            console.error('Failed to load investigation:', e);
        }
    };

    // Start investigation
    const startInvestigation = async () => {
        const q = query || SUGGESTED_QUERIES[0].query;
        setIsRunning(true);
        setStatus('scanning');
        setCurrentAgent('signal_scanner');
        setSignals([]);
        setReports([]);
        setProgressMessages(['Starting investigation...']);
        setReasoningTrace([]);
        setInvestigation(null);
        setShowReasoning(true);

        try {
            const result = await apiPost('/investigate', { query: q });
            const invId = result.investigation_id;
            setInvestigation({ id: invId, status: 'scanning' });
            connectWebSocket(invId);

            // Poll for completion
            const pollInterval = setInterval(async () => {
                try {
                    const inv = await apiGet(`/investigations/${invId}`);
                    setInvestigation(inv);
                    setSignals(inv.signals || []);
                    setReports(inv.reports || []);
                    setProgressMessages(inv.progress || []);
                    setReasoningTrace(inv.reasoning_trace || []);
                    setStatus(inv.status);

                    if (inv.status === 'complete' || inv.status === 'error') {
                        setIsRunning(false);
                        clearInterval(pollInterval);
                    }
                } catch (e) { /* continue polling */ }
            }, 3000);

        } catch (e) {
            setStatus('error');
            setIsRunning(false);
            setProgressMessages(prev => [...prev, `Error: ${e.message}`]);
        }
    };

    const highPriorityCount = signals.filter(s => ['HIGH', 'CRITICAL'].includes(s.priority)).length;

    return (
        <div className="app">
            {/* Header */}
            <header className="header">
                <div className="header-brand">
                    <div className="header-logo">💊</div>
                    <div>
                        <div className="header-title">PharmaVigil AI</div>
                        <div className="header-subtitle">Autonomous Drug Safety Signal Detection</div>
                    </div>
                </div>
                <div className="header-actions">
                    <div className="header-status">
                        <div className={`status-dot ${health?.status === 'healthy' ? '' : 'disconnected'}`} />
                        {health?.status === 'healthy' ? 'Elastic Connected' : 'Connecting...'}
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="main-content">
                {/* KPI Cards */}
                <div className="kpi-row">
                    <KPICard
                        label="Signals Detected"
                        value={signals.length}
                        colorClass="blue"
                        detail={highPriorityCount > 0 ? `${highPriorityCount} high priority` : 'No critical signals'}
                    />
                    <KPICard
                        label="Investigations"
                        value={investigation ? 1 : 0}
                        colorClass="orange"
                        detail={status !== 'idle' ? `Status: ${status}` : 'Ready'}
                    />
                    <KPICard
                        label="Reports Generated"
                        value={reports.length}
                        colorClass="violet"
                        detail={reports.length > 0 ? `${reports.filter(r => r.risk_level === 'HIGH' || r.risk_level === 'CRITICAL').length} high risk` : 'None yet'}
                    />
                    <KPICard
                        label="Agents Active"
                        value={health?.agents_registered || 0}
                        colorClass="emerald"
                        detail={`${health?.tools_registered || 0} ES|QL tools`}
                    />
                </div>

                {/* Investigation Panel */}
                <div className="dashboard-grid full-width">
                    <div className="card investigation-panel animate-slide-up">
                        <div className="card-header">
                            <div className="card-title">
                                <span className="card-title-icon">⚡</span>
                                Investigation Control
                            </div>
                            {isRunning && <span className="spinner" />}
                        </div>
                        <div className="card-body">
                            {/* Natural Language Query Input + Suggestions */}
                            <div className="investigation-trigger">
                                <div className="query-input-wrapper">
                                    <input
                                        type="text"
                                        className="investigation-input"
                                        value={query}
                                        onChange={(e) => setQuery(e.target.value)}
                                        placeholder="Ask PharmaVigil AI anything... e.g. 'Are there cardiac signals for Cardizol-X?'"
                                        disabled={isRunning}
                                        onKeyDown={(e) => e.key === 'Enter' && !isRunning && startInvestigation()}
                                    />
                                </div>
                                <button
                                    className="btn btn-primary"
                                    onClick={startInvestigation}
                                    disabled={isRunning}
                                >
                                    {isRunning ? 'Investigating...' : '🔍 Investigate'}
                                </button>
                            </div>

                            {/* Query Suggestion Chips (Gap #2) */}
                            <QuerySuggestions onSelect={setQuery} disabled={isRunning} />

                            <PipelineSteps currentAgent={currentAgent} status={status} />
                            <ProgressLog messages={progressMessages} />
                        </div>
                    </div>
                </div>

                {/* Agent Reasoning Panel (Gap #1) */}
                {(status !== 'idle' || reasoningTrace.length > 0) && (
                    <div className="dashboard-grid full-width">
                        <div className="card reasoning-card animate-slide-up">
                            <div className="card-header">
                                <div className="card-title">
                                    <span className="card-title-icon">🧠</span>
                                    Agent Reasoning Trace
                                    {reasoningTrace.length > 0 && (
                                        <span className="reasoning-badge">{reasoningTrace.length} steps</span>
                                    )}
                                </div>
                                <button
                                    className="reasoning-view-toggle"
                                    onClick={() => setShowReasoning(!showReasoning)}
                                >
                                    {showReasoning ? 'Hide' : 'Show'} Reasoning
                                </button>
                            </div>
                            {showReasoning && (
                                <div className="card-body" style={{ padding: 0 }}>
                                    <AgentReasoningPanel
                                        reasoningTrace={reasoningTrace}
                                        isRunning={isRunning}
                                    />
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Signals + Chart */}
                <div className="dashboard-grid">
                    <div className="card animate-slide-up">
                        <div className="card-header">
                            <div className="card-title">
                                <span className="card-title-icon">🚨</span>
                                Detected Safety Signals
                            </div>
                        </div>
                        <div className="card-body">
                            <SignalTable signals={signals} />
                        </div>
                    </div>

                    <div className="card animate-slide-up">
                        <div className="card-header">
                            <div className="card-title">
                                <span className="card-title-icon">📊</span>
                                Signal Strength (PRR)
                            </div>
                        </div>
                        <div className="card-body">
                            {signals.length > 0 ? (
                                <SignalChart signals={signals} />
                            ) : (
                                <div className="empty-state">
                                    <div className="empty-state-icon">📊</div>
                                    <div className="empty-state-text">PRR chart will appear after signals are detected</div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Safety Reports */}
                <div className="dashboard-grid full-width">
                    <div className="card report-viewer animate-slide-up">
                        <div className="card-header">
                            <div className="card-title">
                                <span className="card-title-icon">📋</span>
                                Drug Safety Assessment Reports
                            </div>
                        </div>
                        <div className="card-body">
                            <ReportViewer reports={reports} />
                        </div>
                    </div>
                </div>
            </main>

            {/* Footer */}
            <footer style={{
                textAlign: 'center',
                padding: '16px 32px',
                borderTop: '1px solid var(--border-subtle)',
                color: 'var(--text-muted)',
                fontSize: '12px',
            }}>
                PharmaVigil AI — Powered by Elastic Agent Builder + LangGraph | Elasticsearch Agent Builder Hackathon 2026
            </footer>
        </div>
    );
}
