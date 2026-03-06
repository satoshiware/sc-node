import React, { useState } from 'react'
import { SiBitcoin } from 'react-icons/si'
import { login as apiLogin, register as apiRegister } from '../api/auth'

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
    <div className="min-h-screen flex flex-col items-center justify-center p-4 bg-gray-900">
      {/* Centered brand with Bitcoin logo */}
      <div className="flex flex-col items-center justify-center mb-8">
        <SiBitcoin className="w-14 h-14 sm:w-16 sm:h-16 text-amber-500 mb-3" aria-hidden />
        <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight text-center">
          Slim's circle <span className="text-blue-400">Exchange</span>
        </h1>
      </div>

      <div className="w-full max-w-sm bg-gray-800 rounded-lg border border-gray-700 p-6 sm:p-8 shadow-lg">
        <h2 className="text-lg font-semibold text-gray-100 mb-6">
          {mode === 'signup' ? 'Create account' : 'Sign in'}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="text-sm text-red-400 bg-red-900/30 border border-red-800 rounded px-3 py-2">
              {error}
            </div>
          )}

          {mode === 'signup' && (
            <div>
              <label htmlFor="signup-name" className="block text-xs text-gray-400 mb-1">
                Name
              </label>
              <input
                id="signup-name"
                type="text"
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-md px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                placeholder="Your name"
              />
            </div>
          )}

          <div>
            <label htmlFor="login-email" className="block text-xs text-gray-400 mb-1">
              Email
            </label>
            <input
              id="login-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded-md px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label htmlFor="login-password" className="block text-xs text-gray-400 mb-1">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded-md px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              placeholder="••••••••"
            />
          </div>

          {mode === 'signup' && (
            <div>
              <label htmlFor="signup-confirm" className="block text-xs text-gray-400 mb-1">
                Confirm password
              </label>
              <input
                id="signup-confirm"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-md px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                placeholder="••••••••"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium rounded-md transition-colors"
          >
            {loading
              ? (mode === 'signup' ? 'Creating account…' : 'Signing in…')
              : (mode === 'signup' ? 'Sign up' : 'Sign in')}
          </button>

          <button
            type="button"
            onClick={switchMode}
            className="w-full text-sm text-gray-400 hover:text-gray-200 pt-1"
          >
            {mode === 'signup'
              ? 'Already have an account? Sign in'
              : "Don't have an account? Sign up"}
          </button>
        </form>
      </div>
    </div>
  )
}
