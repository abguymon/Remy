import { Outlet, Link, useLocation } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import { Home, ShoppingCart, Settings, LogOut, ChefHat } from 'lucide-react'

export default function Layout() {
  const location = useLocation()
  const { user, logout } = useAuthStore()

  const navItems = [
    { path: '/', icon: Home, label: 'Home' },
    { path: '/cart', icon: ShoppingCart, label: 'Cart' },
    { path: '/settings', icon: Settings, label: 'Settings' },
  ]

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-4 border-b border-gray-200">
          <Link to="/" className="flex items-center gap-2 text-xl font-bold text-primary-600">
            <ChefHat className="w-8 h-8" />
            Remy
          </Link>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-4 py-2 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                <item.icon className="w-5 h-5" />
                {item.label}
              </Link>
            )
          })}
        </nav>

        <div className="p-4 border-t border-gray-200">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-600">{user?.username}</span>
            <button
              onClick={() => {
                logout()
                window.location.href = '/login'
              }}
              className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
              title="Logout"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
