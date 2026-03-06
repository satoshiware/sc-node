import React, { useState } from 'react'
import { SiBitcoin } from 'react-icons/si'
import { login as apiLogin, register as apiRegister } from '../api/auth'

// Mock market stats
const MOCK_STATS = {
  pair: 'BTC/AZC',
  lastPrice: '89,406',
  change24h: '+1.24%',
  volume24h: '$2.4M',
  high24h: '90,120',
  low24h: '88,200',
}

export default function Login({ onLogin }) {
  const [mode, setMode] = useState('login') // 'login' | 'signup'
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function handleSubmit(e) {
    e.preventDefault()
    setError('')

    const trimmedEmail = email.trim()
    if (!trimmedEmail) {
      setError('Email is required')
      return
    }
    if (!password) {
      setError('Password is required')
      return
    }
    if (mode === 'signup') {
      if (!name.trim()) {
        setError('Name is required')
        return
      }
      if (password !== confirmPassword) {
        setError('Passwords do not match')
        return
      }
      if (password.length < 6) {
        setError('Password must be at least 6 characters')
        return
      }
    }

    setLoading(true)
    const authFn = mode === 'signup' ? apiRegister : apiLogin
    const args = mode === 'signup'
      ? [trimmedEmail, password, name.trim()]
      : [trimmedEmail, password]

    authFn(...args)
      .then((userData) => onLogin(userData))
      .catch((err) => {
        const msg = err.message || ''
        // Fallback only for connectivity issues (API down, CORS, 404); show error for auth failures (401)
        const isAuthError = msg.includes('Invalid') || msg.includes('already registered') || msg.includes('401')
        if (isAuthError) {
          setError(msg)
        } else {
          const displayName = mode === 'signup' ? name.trim() : (trimmedEmail.split('@')[0] || 'User')
          onLogin({ id: Date.now(), name: displayName, email: trimmedEmail })
        }
      })
      .finally(() => setLoading(false))
  }

  function switchMode() {
    setMode((m) => (m === 'login' ? 'signup' : 'login'))
    setError('')
    setConfirmPassword('')
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-900">
      {/* Header */}
      <header className="sticky top-0 z-50 w-full bg-gray-900/95 backdrop-blur-sm border-b-2 border-gray-700/80 shadow-[0_4px_20px_rgba(0,0,0,0.3)]">
        <div className="flex items-center justify-center gap-3 py-4 px-6">
          <div className="flex items-center justify-center w-12 h-12 sm:w-14 sm:h-14 rounded-xl bg-gray-800 border-2 border-amber-500/50 shadow-[0_0_20px_rgba(251,191,36,0.3),0_4px_12px_rgba(0,0,0,0.4)]">
            <SiBitcoin className="w-7 h-7 sm:w-8 sm:h-8 text-amber-500 drop-shadow-[0_0_8px_rgba(251,191,36,0.6)]" aria-hidden />
          </div>
          <h1 className="text-xl sm:text-2xl md:text-3xl font-extrabold text-white tracking-tight">
            Slim's Circle P2P Exchange <span className="text-blue-400">AZCoins/ SATS</span>
          </h1>
        </div>
      </header>

      {/* Centered brand with Bitcoin logo (hero section) */}
      <div className="flex flex-col items-center justify-center py-8 md:py-10 px-4">
        <div className="flex items-center justify-center w-20 h-20 sm:w-24 sm:h-24 md:w-28 md:h-28 rounded-2xl bg-gray-800/90 border-2 border-amber-500/40 shadow-[0_0_30px_rgba(251,191,36,0.25),0_8px_24px_rgba(0,0,0,0.5)] mb-4 md:mb-5">
          <SiBitcoin className="w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 text-amber-500 drop-shadow-[0_0_12px_rgba(251,191,36,0.6),0_2px_4px_rgba(0,0,0,0.3)]" aria-hidden />
        </div>
        <h2 className="text-xl sm:text-2xl md:text-3xl font-bold text-white tracking-tight text-center">
          Slim's circle <span className="text-blue-400">Exchange</span>
        </h2>
        <p className="mt-2 text-sm sm:text-base text-gray-400">Trade with confidence</p>
      </div>

      {/* Two-column layout: form + market stats */}
      <div className="flex-1 flex flex-col lg:flex-row items-center justify-center gap-6 md:gap-8 lg:gap-12 px-4 pb-8 md:px-6 md:pb-10">
        {/* Form column */}
        <div className="w-full max-w-sm bg-gray-800 rounded-xl border-2 border-gray-600/80 p-5 sm:p-6 md:p-8 shadow-[0_8px_32px_rgba(0,0,0,0.4),0_0_0_1px_rgba(255,255,255,0.05)]">
          <h2 className="text-lg sm:text-xl font-bold text-gray-100 mb-5 md:mb-6">
            {mode === 'signup' ? 'Create account' : 'Sign in'}
          </h2>

          <form onSubmit={handleSubmit} className="space-y-3 md:space-y-4">
          {error && (
            <div className="text-xs sm:text-sm text-red-400 bg-red-900/40 border-2 border-red-700/60 rounded-lg px-3 py-2.5 shadow-inner">
              {error}
            </div>
          )}

          {mode === 'signup' && (
            <div>
              <label htmlFor="signup-name" className="block text-sm font-medium text-gray-400 mb-1.5">
                Name
              </label>
              <input
                id="signup-name"
                type="text"
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-gray-900 border-2 border-gray-600 rounded-lg px-3 py-2.5 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm sm:text-base"
                placeholder="Your name"
              />
            </div>
          )}

          <div>
            <label htmlFor="login-email" className="block text-sm font-medium text-gray-400 mb-1.5">
              Email
            </label>
            <input
              id="login-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-gray-900 border-2 border-gray-600 rounded-lg px-3 py-2.5 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm sm:text-base"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label htmlFor="login-password" className="block text-sm font-medium text-gray-400 mb-1.5">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-gray-900 border-2 border-gray-600 rounded-lg px-3 py-2.5 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm sm:text-base"
              placeholder="••••••••"
            />
          </div>

          {mode === 'signup' && (
            <div>
              <label htmlFor="signup-confirm" className="block text-sm font-medium text-gray-400 mb-1.5">
                Confirm password
              </label>
              <input
                id="signup-confirm"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full bg-gray-900 border-2 border-gray-600 rounded-lg px-3 py-2.5 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm sm:text-base"
                placeholder="••••••••"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-bold rounded-lg text-base shadow-[0_4px_14px_rgba(59,130,246,0.4)] hover:shadow-[0_6px_20px_rgba(59,130,246,0.5)] transition-all"
          >
            {loading
              ? (mode === 'signup' ? 'Creating account…' : 'Signing in…')
              : (mode === 'signup' ? 'Sign up' : 'Sign in')}
          </button>

          <button
            type="button"
            onClick={switchMode}
            className="w-full text-xs sm:text-sm text-gray-400 hover:text-gray-200 pt-1"
          >
            {mode === 'signup'
              ? 'Already have an account? Sign in'
              : "Don't have an account? Sign up"}
          </button>
        </form>
        </div>

        {/* Market stats / value props column */}
        <div className="w-full max-w-sm lg:max-w-xs bg-gray-800 rounded-xl border-2 border-gray-600/80 p-5 sm:p-6 md:p-6 shadow-[0_8px_32px_rgba(0,0,0,0.4),0_0_0_1px_rgba(255,255,255,0.05)]">
          <h3 className="text-base sm:text-lg font-bold text-gray-200 mb-4 md:mb-5">
            Market overview
          </h3>
          <div className="space-y-2.5 md:space-y-3.5 text-sm sm:text-base">
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Pair</span>
              <span className="text-gray-200 font-medium">{MOCK_STATS.pair}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Last price</span>
              <span className="text-white font-medium">{MOCK_STATS.lastPrice}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">24h change</span>
              <span className="text-green-400 font-medium">{MOCK_STATS.change24h}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">24h volume</span>
              <span className="text-gray-200">{MOCK_STATS.volume24h}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">24h high</span>
              <span className="text-gray-200">{MOCK_STATS.high24h}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">24h low</span>
              <span className="text-gray-200">{MOCK_STATS.low24h}</span>
            </div>
          </div>
          <p className="mt-5 md:mt-6 text-sm text-gray-500 font-medium">
            Trade BTC/AZC with low fees. Secure and fast execution.
          </p>
        </div>
      </div>

      {/* Footer */}
      <footer className="py-5 md:py-6 px-4 border-t-2 border-gray-800 bg-gray-900/50 shadow-[0_-4px_20px_rgba(0,0,0,0.2)]">
        <div className="flex flex-wrap justify-center gap-6 sm:gap-8 text-sm font-medium text-gray-500">
          <a href="#" className="hover:text-gray-300 transition-colors">Terms</a>
          <a href="#" className="hover:text-gray-300 transition-colors">Privacy</a>
          <a href="#" className="hover:text-gray-300 transition-colors">Support</a>
        </div>
      </footer>
    </div>
  )
}
