import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles.css';

// No <StrictMode>: React 19's dev-only double mount unmounts the WebGL canvas while it is rendering, which
// logs a scary (harmless) error. The app has no effects that need the double-invoke check.
createRoot(document.getElementById('root')!).render(<App />);
