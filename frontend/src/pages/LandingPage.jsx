import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
    HiOutlineShieldCheck,
    HiOutlineLightningBolt,
    HiOutlineDocumentReport,
    HiOutlineChartBar,
    HiOutlineGlobeAlt,
    HiOutlineChip,
} from 'react-icons/hi';
import {
    FiArrowRight,
    FiActivity,
    FiDatabase,
    FiCpu,
    FiZap,
    FiTrendingUp,
    FiUsers,
    FiLock
} from 'react-icons/fi';
import './LandingPage.css';

const FEATURES = [
    {
        icon: <HiOutlineShieldCheck />,
        title: 'Signal Detection',
        desc: 'AI-powered scanning of 500K+ FAERS reports to detect emerging drug safety signals with statistical rigor.',
        color: 'var(--accent-primary)',
    },
    {
        icon: <HiOutlineChartBar />,
        title: 'Deep Investigation',
        desc: 'Automated case analysis across demographics, drug interactions, outcome severity, and geographic patterns.',
        color: 'var(--accent-secondary)',
    },
    {
        icon: <HiOutlineDocumentReport />,
        title: 'Safety Reports',
        desc: 'Comprehensive regulatory-ready reports generated in seconds, not weeks. ICH E2B compliant.',
        color: 'var(--accent-tertiary)',
    },
];

const STATS = [
    { value: '500K+', label: 'FAERS Records', icon: <FiDatabase /> },
    { value: '3', label: 'AI Agents', icon: <FiCpu /> },
    { value: '<30s', label: 'Detection Time', icon: <FiZap /> },
    { value: '99.9%', label: 'Uptime SLA', icon: <FiActivity /> },
];

const PIPELINE_STEPS = [
    {
        num: '01',
        title: 'Master Orchestrator',
        desc: 'Intelligent routing classifies your query and dispatches to the optimal agent pipeline.',
        icon: <FiCpu />,
        color: 'var(--accent-tertiary)',
    },
    {
        num: '02',
        title: 'Signal Scanner',
        desc: 'Scans FAERS database computing PRR, spike ratios, and statistical anomalies across all drugs.',
        icon: <FiTrendingUp />,
        color: 'var(--accent-primary)',
    },
    {
        num: '03',
        title: 'Case Investigator',
        desc: 'Deep-dives into flagged signals analyzing demographics, concomitant drugs, and outcome severity.',
        icon: <HiOutlineChartBar />,
        color: 'var(--accent-warning)',
    },
    {
        num: '04',
        title: 'Safety Reporter',
        desc: 'Compiles findings into structured, evidence-based safety assessment reports with regulatory guidance.',
        icon: <HiOutlineDocumentReport />,
        color: 'var(--accent-secondary)',
    },
];

export default function LandingPage() {
    const navigate = useNavigate();
    const { user } = useAuth();

    return (
        <div className="landing-page">
            <div className="app-bg" />

            {/* ── Navbar ──────────────────── */}
            <nav className="landing-nav glass-card-static">
                <div className="container flex items-center justify-between">
                    <div className="nav-brand flex items-center gap-md">
                        <div className="nav-logo">
                            <HiOutlineShieldCheck />
                        </div>
                        <div>
                            <span className="nav-title">PharmaVigil</span>
                            <span className="nav-badge">AI</span>
                        </div>
                    </div>
                    <div className="nav-links hide-mobile">
                        <a href="#features">Features</a>
                        <a href="#pipeline">How It Works</a>
                        <a href="#stats">Stats</a>
                    </div>
                    <div className="nav-actions flex gap-md">
                        {user ? (
                            <button className="btn btn-primary" onClick={() => navigate('/app')}>
                                Open Dashboard <FiArrowRight />
                            </button>
                        ) : (
                            <>
                                <button className="btn btn-ghost" onClick={() => navigate('/auth?mode=login')}>
                                    Sign In
                                </button>
                                <button className="btn btn-primary" onClick={() => navigate('/auth?mode=signup')}>
                                    Get Started <FiArrowRight />
                                </button>
                            </>
                        )}
                    </div>
                </div>
            </nav>

            {/* ── Hero ────────────────────── */}
            <section className="hero-section">
                <div className="container">
                    <div className="hero-content">
                        <div className="hero-badge anim-fade-in-down">
                            <FiZap /> Powered by Elastic Agent Builder + LangGraph
                        </div>
                        <h1 className="heading-xl anim-fade-in-up">
                            Autonomous Drug Safety<br />
                            <span className="gradient-text">Signal Detection</span>
                        </h1>
                        <p className="hero-subtitle anim-fade-in-up anim-delay-2">
                            Multi-agent AI system that continuously monitors FDA adverse event reports,
                            detects emerging safety signals, investigates cases, and generates
                            regulatory-ready reports — all in under 30 seconds.
                        </p>
                        <div className="hero-actions anim-fade-in-up anim-delay-3">
                            <button className="btn btn-primary btn-lg" onClick={() => navigate(user ? '/app' : '/auth?mode=signup')}>
                                Start Investigation <FiArrowRight />
                            </button>
                            <button className="btn btn-ghost btn-lg" onClick={() => document.getElementById('pipeline')?.scrollIntoView({ behavior: 'smooth' })}>
                                See How It Works
                            </button>
                        </div>
                        <div className="hero-trust anim-fade-in-up anim-delay-4">
                            <div className="trust-item"><FiLock /> Enterprise Security</div>
                            <div className="trust-item"><FiUsers /> SOC 2 Compliant</div>
                            <div className="trust-item"><HiOutlineGlobeAlt /> Global Coverage</div>
                        </div>
                    </div>

                    {/* Hero Visual */}
                    <div className="hero-visual anim-fade-in anim-delay-3">
                        <div className="hero-glow" />
                        <div className="hero-dashboard-preview glass-card">
                            <div className="preview-header">
                                <div className="preview-dots">
                                    <span /><span /><span />
                                </div>
                                <span className="preview-title font-mono text-xs text-muted">PharmaVigil Dashboard</span>
                            </div>
                            <div className="preview-body">
                                <div className="preview-pipeline">
                                    {['Orchestrator', 'Scanner', 'Investigator', 'Reporter'].map((name, i) => (
                                        <div key={name} className={`preview-step ${i <= 2 ? 'active' : ''}`}>
                                            <div className="step-dot" />
                                            <span>{name}</span>
                                        </div>
                                    ))}
                                </div>
                                <div className="preview-signals">
                                    {['Cardizol-X → Cardiac Arrest', 'Neurofen-Plus → Seizure', 'Arthrex-200 → Renal Failure'].map((sig, i) => (
                                        <div key={i} className="preview-signal-row">
                                            <span className={`signal-badge ${['critical', 'high', 'medium'][i]}`}>
                                                {['CRITICAL', 'HIGH', 'MEDIUM'][i]}
                                            </span>
                                            <span className="font-mono text-xs">{sig}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* ── Stats Bar ──────────────── */}
            <section className="stats-section" id="stats">
                <div className="container">
                    <div className="stats-grid">
                        {STATS.map((stat) => (
                            <div key={stat.label} className="stat-card glass-card">
                                <div className="stat-icon">{stat.icon}</div>
                                <div className="stat-value">{stat.value}</div>
                                <div className="stat-label">{stat.label}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── Features ───────────────── */}
            <section className="features-section" id="features">
                <div className="container">
                    <div className="section-header text-center">
                        <h2 className="heading-lg">
                            Enterprise-Grade <span className="gradient-text">Pharmacovigilance</span>
                        </h2>
                        <p className="text-secondary text-lg">
                            Three specialized AI agents work together to deliver comprehensive drug safety intelligence.
                        </p>
                    </div>
                    <div className="features-grid">
                        {FEATURES.map((feat, i) => (
                            <div key={feat.title} className={`feature-card glass-card anim-fade-in-up anim-delay-${i + 1}`}>
                                <div className="feature-icon" style={{ color: feat.color, borderColor: feat.color }}>
                                    {feat.icon}
                                </div>
                                <h3 className="heading-sm">{feat.title}</h3>
                                <p className="text-secondary">{feat.desc}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── Pipeline ───────────────── */}
            <section className="pipeline-section" id="pipeline">
                <div className="container">
                    <div className="section-header text-center">
                        <h2 className="heading-lg">
                            How <span className="gradient-text">It Works</span>
                        </h2>
                        <p className="text-secondary text-lg">
                            A multi-agent pipeline orchestrated by LangGraph, powered by Elastic Agent Builder.
                        </p>
                    </div>
                    <div className="pipeline-grid">
                        {PIPELINE_STEPS.map((step, i) => (
                            <div key={step.num} className="pipeline-card glass-card">
                                <div className="pipeline-num" style={{ color: step.color }}>{step.num}</div>
                                <div className="pipeline-icon" style={{ color: step.color }}>{step.icon}</div>
                                <h3 className="heading-sm">{step.title}</h3>
                                <p className="text-secondary text-sm">{step.desc}</p>
                                {i < PIPELINE_STEPS.length - 1 && <div className="pipeline-connector" />}
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── CTA Footer ─────────────── */}
            <section className="cta-section">
                <div className="container text-center">
                    <div className="cta-card glass-card-static">
                        <h2 className="heading-lg">
                            Ready to Detect Safety Signals <span className="gradient-text">Faster?</span>
                        </h2>
                        <p className="text-secondary text-lg" style={{ maxWidth: 600, margin: '0 auto' }}>
                            Join pharmaceutical companies worldwide using AI-powered pharmacovigilance
                            to protect patient safety.
                        </p>
                        <div className="flex justify-center gap-lg" style={{ marginTop: 'var(--space-xl)' }}>
                            <button className="btn btn-primary btn-lg" onClick={() => navigate(user ? '/app' : '/auth?mode=signup')}>
                                Get Started Free <FiArrowRight />
                            </button>
                        </div>
                    </div>
                </div>
            </section>

            {/* ── Footer ─────────────────── */}
            <footer className="landing-footer">
                <div className="container flex justify-between items-center">
                    <div className="flex items-center gap-md">
                        <HiOutlineShieldCheck style={{ color: 'var(--accent-primary)', fontSize: '1.2rem' }} />
                        <span className="text-sm text-muted">
                            © 2026 PharmaVigil AI. Built for Elastic Hackathon.
                        </span>
                    </div>
                    <div className="flex gap-lg text-sm text-muted hide-mobile">
                        <span>Powered by Elastic</span>
                        <span>•</span>
                        <span>LangGraph</span>
                        <span>•</span>
                        <span>Groq</span>
                    </div>
                </div>
            </footer>
        </div>
    );
}
