import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AppShell from './components/AppShell'
import Login from './screens/Login'
import Join from './screens/Join'
import Landing from './screens/Landing'
import Cookbook from './screens/Cookbook'
import RecipeDetail from './screens/RecipeDetail'
import CartRecord from './screens/CartRecord'
import Settings from './screens/Settings'
import NotFound from './screens/NotFound'
import PlanFlow from './screens/plan/PlanFlow'
import { useAuth } from './stores/auth'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuth((s) => s.token)
  const location = useLocation()
  if (!token) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route index element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/join" element={<Join />} />
      <Route
        path="/app"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<PlanFlow />} />
        <Route path="cookbook" element={<Cookbook />} />
        <Route path="cookbook/:id" element={<RecipeDetail />} />
        <Route path="cart" element={<CartRecord />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
      <Route path="/cookbook/*" element={<Navigate to="/app/cookbook" replace />} />
      <Route path="/cart" element={<Navigate to="/app/cart" replace />} />
      <Route path="/settings" element={<Navigate to="/app/settings" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
