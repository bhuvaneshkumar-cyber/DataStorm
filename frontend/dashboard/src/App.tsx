import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import Login from './pages/Login';
import Register from './pages/Register';
import WorkerLayout from './layouts/WorkerLayout';
import LenderLayout from './layouts/LenderLayout';
import Overview from './pages/worker/Overview';
import Expenses from './pages/worker/Expenses';
import Platforms from './pages/worker/Platforms';
import Credit from './pages/worker/Credit';
import Loans from './pages/worker/Loans';
import Insurance from './pages/worker/Insurance';
import Tax from './pages/worker/Tax';
import LenderDashboard from './pages/lender/LenderDashboard';

function App() {
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      import('./lib/api').then(api => {
        api.getProfile()
          .then(u => setUser(u))
          .catch(() => localStorage.removeItem('auth_token'))
          .finally(() => setLoading(false));
      });
    } else {
      setLoading(false);
    }
  }, []);

  if (loading) return <div className="loading-screen">Loading...</div>;

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={!user ? <Login setUser={setUser} /> : <Navigate to={user.role === 'lender' ? '/lender' : '/'} />} />
        <Route path="/register" element={!user ? <Register setUser={setUser} /> : <Navigate to="/" />} />

        <Route path="/" element={user?.role === 'worker' ? <WorkerLayout user={user} setUser={setUser} /> : <Navigate to="/login" />}>
          <Route index element={<Overview />} />
          <Route path="expenses" element={<Expenses />} />
          <Route path="platforms" element={<Platforms />} />
          <Route path="credit" element={<Credit />} />
          <Route path="loans" element={<Loans />} />
          <Route path="insurance" element={<Insurance />} />
          <Route path="tax" element={<Tax />} />
        </Route>

        <Route path="/lender" element={user?.role === 'lender' ? <LenderLayout user={user} setUser={setUser} /> : <Navigate to="/login" />}>
          <Route index element={<LenderDashboard />} />
        </Route>

        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
