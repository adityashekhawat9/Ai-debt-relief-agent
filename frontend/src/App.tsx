import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import BrowserTest from './pages/BrowserTest';
import { Laptop } from 'lucide-react';
import './index.css';

function App() {
  return (
    <BrowserRouter>
      {/* Global Navigation */}
      <nav style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        padding: '1rem',
        display: 'flex',
        justifyContent: 'center',
        gap: '2rem',
        background: 'rgba(0,0,0,0.5)',
        backdropFilter: 'blur(10px)',
        zIndex: 50,
        borderBottom: '1px solid rgba(255,255,255,0.1)'
      }}>
        <Link to="/" style={{ color: 'white', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600 }}>
          <Laptop size={20} /> Browser Test
        </Link>

      </nav>

      {/* Main Content */}
      <div style={{ paddingTop: '60px', height: '100vh' }}>
        <Routes>
          <Route path="/" element={<BrowserTest />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
