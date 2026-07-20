import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AppShell from './components/AppShell'
import Login from './screens/Login'
import Join from './screens/Join'
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
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/join" element={<Join />} />
      <Route
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
    </Routes>
  )
}
