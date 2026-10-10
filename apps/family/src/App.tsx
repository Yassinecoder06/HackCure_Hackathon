import React, { useState } from 'react';
import { STRINGS } from './i18n/strings';
import { familyApi } from './services/familyApi';
import { RedeemInvite } from './pages/RedeemInvite';
import { FamilyFeedView } from './pages/FamilyFeedView';
import './styles/index.css';

export const App: React.FC = () => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => familyApi.hasSession());

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
