import { Link, Outlet, useLocation } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/projects', label: '小说项目' },
  { to: '/settings/providers', label: '服务商' },
  { to: '/settings/prompts', label: '提示词' },
  { to: '/settings/workflows', label: '工作流' },
]

export function AppShell() {
  const location = useLocation()

  return (
    <div className="flex h-screen">
      <nav className="w-56 bg-gray-900 text-white flex flex-col shrink-0">
        <div className="px-4 py-3 text-lg font-semibold border-b border-gray-700">
          小说工作台
        </div>
        <ul className="flex-1 space-y-1 p-2">
          {NAV_ITEMS.map((item) => {
            const active = location.pathname.startsWith(item.to)
            return (
              <li key={item.to}>
                <Link
                  to={item.to}
                  className={`block px-3 py-2 rounded text-sm transition-colors ${
                    active
                      ? 'bg-gray-700 text-white'
                      : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                  }`}
                >
                  {item.label}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>
      <main className="flex-1 overflow-auto bg-gray-50">
        <Outlet />
      </main>
    </div>
  )
}
