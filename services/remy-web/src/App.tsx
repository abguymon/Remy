import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AppShell from './components/AppShell'
import Login from './screens/Login'
import Stub from './screens/Stub'
import NotFound from './screens/NotFound'
import PlanFlow from './screens/plan/PlanFlow'
import { useAuth } from './stores/auth'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuth((s) => s.token)
  const location = useLocation()
  if (!token) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<PlanFlow />} />
        <Route path="cookbook" element={<Stub title="Cookbook" glyph="📖" />} />
        <Route path="cart" element={<Stub title="Cart" glyph="🛒" />} />
        <Route path="settings" element={<Stub title="Settings" glyph="⚙" />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
