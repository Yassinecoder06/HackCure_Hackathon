import React, { useState, useEffect } from 'react';
import { DICTIONARY, Language } from './i18n/strings';
import { familyApi } from './services/familyApi';
import { RedeemInvite } from './pages/RedeemInvite';
import { FamilyFeedView } from './pages/FamilyFeedView';
import { Sun, Moon, Languages } from 'lucide-react';
import './styles/index.css';

export const App: React.FC = () => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => familyApi.hasSession());
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    return (localStorage.getItem('borj_family_theme') as 'light' | 'dark') || 'light';
  });
  const [lang, setLang] = useState<Language>(() => {
    return (localStorage.getItem('borj_family_lang') as Language) || 'fr';
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

  const handleToggleLang = () => {
    const nextLang = lang === 'fr' ? 'en' : 'fr';
    setLang(nextLang);
    localStorage.setItem('borj_family_lang', nextLang);
  };

  const t = DICTIONARY[lang];

  return (
    <div className="family-app-wrapper">
      <header className="family-header">
        <div className="header-brand">
          <div className="brand-icon">FC</div>
          <div className="header-titles">
            <h1>{t.app.title}</h1>
            <p>{t.app.hospitalName}</p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Language Switcher Button */}
          <button
            className="family-lang-btn"
            onClick={handleToggleLang}
            title={lang === 'fr' ? 'Switch to English' : 'Passer en Français'}
            id="btn-family-lang"
          >
            <Languages size={15} />
            <span style={{ fontWeight: 800, fontSize: '0.75rem', letterSpacing: '0.05em' }}>
              {lang === 'fr' ? 'FR 🇫🇷' : 'EN 🇬🇧'}
            </span>
          </button>

          {/* Theme Toggle Button */}
          <button
            className="family-theme-btn"
            onClick={handleToggleTheme}
            title={theme === 'light' ? 'Switch to Night Mode' : 'Switch to Daytime Mode'}
            id="btn-family-theme"
          >
            {theme === 'light' ? <Moon size={17} /> : <Sun size={17} />}
          </button>
        </div>
      </header>

      <main style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
        {!isAuthenticated ? (
          <RedeemInvite lang={lang} onSuccess={() => setIsAuthenticated(true)} />
        ) : (
          <FamilyFeedView
            lang={lang}
            onLogout={() => {
              familyApi.clearSession();
              setIsAuthenticated(false);
            }}
          />
        )}
      </main>
    </div>
  );
};

export default App;
