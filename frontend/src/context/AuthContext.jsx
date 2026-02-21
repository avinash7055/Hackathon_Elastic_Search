import { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const saved = localStorage.getItem('pharma_user');
        if (saved) {
            try {
                setUser(JSON.parse(saved));
            } catch { /* ignore */ }
        }
        setLoading(false);
    }, []);

    const login = (email, password) => {
        return new Promise((resolve, reject) => {
            setTimeout(() => {
                if (!email || !password) {
                    reject(new Error('Email and password are required'));
                    return;
                }
                const userData = {
                    id: 'usr_' + Math.random().toString(36).substr(2, 9),
                    email,
                    name: email.split('@')[0].replace(/[._-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
                    avatar: email.charAt(0).toUpperCase(),
                    joinedAt: new Date().toISOString(),
                };
                setUser(userData);
                localStorage.setItem('pharma_user', JSON.stringify(userData));
                resolve(userData);
            }, 800);
        });
    };

    const signup = (name, email, password) => {
        return new Promise((resolve, reject) => {
            setTimeout(() => {
                if (!name || !email || !password) {
                    reject(new Error('All fields are required'));
                    return;
                }
                if (password.length < 6) {
                    reject(new Error('Password must be at least 6 characters'));
                    return;
                }
                const userData = {
                    id: 'usr_' + Math.random().toString(36).substr(2, 9),
                    email,
                    name,
                    avatar: name.charAt(0).toUpperCase(),
                    joinedAt: new Date().toISOString(),
                };
                setUser(userData);
                localStorage.setItem('pharma_user', JSON.stringify(userData));
                resolve(userData);
            }, 1000);
        });
    };

    const logout = () => {
        setUser(null);
        localStorage.removeItem('pharma_user');
    };

    return (
        <AuthContext.Provider value={{ user, loading, login, signup, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within AuthProvider');
    return ctx;
}
