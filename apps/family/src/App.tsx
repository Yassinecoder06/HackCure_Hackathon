import React, { useState, useEffect } from 'react';
import { STRINGS } from './i18n/strings';
import { familyApi } from './services/familyApi';
import { RedeemInvite } from './pages/RedeemInvite';
import { FamilyFeedView } from './pages/FamilyFeedView';
import { Sun, Moon } from 'lucide-react';
import './styles/index.css';

export const App: React.FC = () => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => familyApi.hasSession());
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    return (localStorage.getItem('borj_family_theme') as 'light' | 'dark') || 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    if (theme === 'dark') {
      document.body.classList.add('dark-mode');
      document.body.classList.remove('light-mode');
    } else {
      document.body.classList.add('light-mode');
      document.body.classList.remove('dark-mode');
    }
    localStorage.setItem('borj_family_theme', theme);
  }, [theme]);

  const handleToggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  return (
    <div className="family-app-wrapper">
      <header className="family-header">
        <div className="header-brand">
          <div className="brand-icon">FC</div>
          <div className="header-titles">
            <h1>{STRINGS.app.title}</h1>
            <p>{STRINGS.app.hospitalName}</p>
          </div>
        </div>

        <button
          className="family-theme-btn"
          onClick={handleToggleTheme}
          title={theme === 'light' ? 'Switch to Night Mode' : 'Switch to Daytime Mode'}
          id="btn-family-theme"
          style={{
            background: 'rgba(255, 255, 255, 0.15)',
            border: '1px solid rgba(255, 255, 255, 0.25)',
            borderRadius: 8,
            width: 34,
            height: 34,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#ffffff',
            cursor: 'pointer',
            transition: 'background 0.2s ease'
          }}
        >
          {theme === 'light' ? <Moon size={17} /> : <Sun size={17} />}
        </button>
      </header>

      <main style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
        {!isAuthenticated ? (
          <RedeemInvite onSuccess={() => setIsAuthenticated(true)} />
        ) : (
          <FamilyFeedView onLogout={() => {
            familyApi.clearSession();
            setIsAuthenticated(false);
          }} />
        )}
      </main>
    </div>
  );
};

export default App;
