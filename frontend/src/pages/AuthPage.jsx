import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { HiOutlineShieldCheck } from 'react-icons/hi';
import { FiMail, FiLock, FiUser, FiArrowRight, FiEye, FiEyeOff } from 'react-icons/fi';
import './AuthPage.css';

export default function AuthPage() {
    const [searchParams] = useSearchParams();
    const [mode, setMode] = useState(searchParams.get('mode') || 'login');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [name, setName] = useState('');
    const [showPass, setShowPass] = useState(false);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();
    const { user, login, signup } = useAuth();

    useEffect(() => {
        if (user) navigate('/app');
    }, [user, navigate]);

    useEffect(() => {
        const m = searchParams.get('mode');
        if (m === 'login' || m === 'signup') setMode(m);
    }, [searchParams]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            if (mode === 'login') {
                await login(email, password);
            } else {
                await signup(name, email, password);
            }
            navigate('/app');
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="auth-page">
            <div className="app-bg" />

            {/* Background orbs */}
            <div className="auth-orb auth-orb-1" />
            <div className="auth-orb auth-orb-2" />
            <div className="auth-orb auth-orb-3" />

            <div className="auth-container anim-fade-in-up">
                {/* Left branding panel */}
                <div className="auth-brand-panel hide-mobile">
                    <div className="auth-brand-content">
                        <div className="nav-logo" style={{ width: 48, height: 48, fontSize: '1.5rem' }}>
                            <HiOutlineShieldCheck />
                        </div>
                        <h2 className="heading-md" style={{ marginTop: 'var(--space-lg)' }}>
                            PharmaVigil <span className="gradient-text">AI</span>
                        </h2>
                        <p className="text-secondary" style={{ marginTop: 'var(--space-md)', lineHeight: 1.7 }}>
                            Autonomous drug safety signal detection powered by multi-agent AI.
                            Protect patients with real-time pharmacovigilance.
                        </p>
                        <div className="auth-brand-features">
                            <div className="brand-feature">
                                <span className="brand-feature-dot" style={{ background: 'var(--accent-primary)' }} />
                                Real-time FAERS monitoring
                            </div>
                            <div className="brand-feature">
                                <span className="brand-feature-dot" style={{ background: 'var(--accent-secondary)' }} />
                                Multi-agent investigation
                            </div>
                            <div className="brand-feature">
                                <span className="brand-feature-dot" style={{ background: 'var(--accent-tertiary)' }} />
                                Automated safety reports
                            </div>
                        </div>
                    </div>
                </div>

                {/* Right form panel */}
                <div className="auth-form-panel">
                    <div className="auth-form-header">
                        <h2 className="heading-md">
                            {mode === 'login' ? 'Welcome back' : 'Create your account'}
                        </h2>
                        <p className="text-secondary text-sm" style={{ marginTop: 'var(--space-sm)' }}>
                            {mode === 'login'
                                ? 'Sign in to access your investigations'
                                : 'Start detecting drug safety signals today'}
                        </p>
                    </div>

                    {/* Mode tabs */}
                    <div className="auth-tabs">
                        <button
                            className={`auth-tab ${mode === 'login' ? 'active' : ''}`}
                            onClick={() => { setMode('login'); setError(''); }}
                        >
                            Sign In
                        </button>
                        <button
                            className={`auth-tab ${mode === 'signup' ? 'active' : ''}`}
                            onClick={() => { setMode('signup'); setError(''); }}
                        >
                            Sign Up
                        </button>
                    </div>

                    <form onSubmit={handleSubmit} className="auth-form">
                        {mode === 'signup' && (
                            <div className="input-group anim-fade-in">
                                <label htmlFor="name">Full Name</label>
                                <div className="input-with-icon">
                                    <FiUser className="input-icon" />
                                    <input
                                        id="name"
                                        className="input"
                                        type="text"
                                        placeholder="Dr. Jane Smith"
                                        value={name}
                                        onChange={e => setName(e.target.value)}
                                        required
                                    />
                                </div>
                            </div>
                        )}

                        <div className="input-group">
                            <label htmlFor="email">Email Address</label>
                            <div className="input-with-icon">
                                <FiMail className="input-icon" />
                                <input
                                    id="email"
                                    className="input"
                                    type="email"
                                    placeholder="jane@pharma.com"
                                    value={email}
                                    onChange={e => setEmail(e.target.value)}
                                    required
                                />
                            </div>
                        </div>

                        <div className="input-group">
                            <label htmlFor="password">Password</label>
                            <div className="input-with-icon">
                                <FiLock className="input-icon" />
                                <input
                                    id="password"
                                    className="input"
                                    type={showPass ? 'text' : 'password'}
                                    placeholder="••••••••"
                                    value={password}
                                    onChange={e => setPassword(e.target.value)}
                                    required
                                    minLength={6}
                                />
                                <button
                                    type="button"
                                    className="pass-toggle"
                                    onClick={() => setShowPass(!showPass)}
                                >
                                    {showPass ? <FiEyeOff /> : <FiEye />}
                                </button>
                            </div>
                        </div>

                        {error && (
                            <div className="auth-error anim-fade-in">
                                {error}
                            </div>
                        )}

                        <button type="submit" className="btn btn-primary w-full" disabled={loading}>
                            {loading ? (
                                <span className="spinner spinner-sm" />
                            ) : (
                                <>
                                    {mode === 'login' ? 'Sign In' : 'Create Account'}
                                    <FiArrowRight />
                                </>
                            )}
                        </button>
                    </form>

                    <div className="auth-footer">
                        <p className="text-xs text-muted text-center">
                            Demo mode — no real authentication. Your data stays in your browser.
                        </p>
                    </div>
                </div>
            </div>

            {/* Back to home */}
            <button
                className="auth-back-btn btn btn-ghost btn-sm"
                onClick={() => navigate('/')}
            >
                ← Back to Home
            </button>
        </div>
    );
}
