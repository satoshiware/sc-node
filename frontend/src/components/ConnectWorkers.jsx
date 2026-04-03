import React, { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { FiCopy, FiX } from 'react-icons/fi'

const STRATUM_V1_URL = 'stratum+tcp://stratum.satoshiware.com:3333'
const STRATUM_V2_URL = 'stratum+tcp://v2.stratum.satoshiware.com:3333'

function poolLoginId(user) {
  if (!user) return 'yourAccount'
  const fromEmail = user.email?.split('@')[0]?.trim()
  if (fromEmail) return fromEmail
  const fromName = user.name?.replace(/\s+/g, '')?.trim()
  if (fromName) return fromName
  return 'yourAccount'
}

export default function ConnectWorkers({ open, onClose, user }) {
  const [protocol, setProtocol] = useState('v1')
  const [copied, setCopied] = useState(false)

  const stratumUrl = protocol === 'v1' ? STRATUM_V1_URL : STRATUM_V2_URL
  const urlLine = useMemo(() => `#1 ${stratumUrl}`, [stratumUrl])
  const loginId = useMemo(() => poolLoginId(user), [user])

  useEffect(() => {
    if (!open) return
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  useEffect(() => {
    if (!open) {
      setProtocol('v1')
      setCopied(false)
    }
  }, [open])

  const copyUrl = async () => {
    try {
      await navigator.clipboard.writeText(stratumUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  if (!open) return null

  const modal = (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6"
      role="presentation"
    >
      <button
        type="button"
        className="absolute inset-0 bg-black/60 backdrop-blur-[2px]"
        aria-label="Close modal"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="connect-workers-title"
        className="relative z-[101] w-full max-w-lg rounded-xl bg-white text-gray-900 shadow-2xl ring-1 ring-black/5"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-gray-200 px-5 py-4">
          <h2 id="connect-workers-title" className="text-lg font-semibold text-gray-900">
            Connect Workers
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-800"
            aria-label="Close"
          >
            <FiX className="h-5 w-5" />
          </button>
        </div>

        <div className="max-h-[min(85vh,640px)] overflow-y-auto px-5 py-4 space-y-5 text-sm text-gray-700">
          <p className="leading-relaxed">
            Braiins Pool servers are located all around the world. For a stable connection and lower latency,{' '}
            <strong className="font-semibold text-gray-900">please select a location</strong> that is closest to your
            mining location.
          </p>

          <div className="space-y-2">
            <div className="text-xs font-medium uppercase tracking-wide text-gray-500">Mining Protocol</div>
            <div className="flex rounded-lg border border-gray-200 p-0.5 bg-gray-50">
              <button
                type="button"
                onClick={() => setProtocol('v1')}
                className={
                  protocol === 'v1'
                    ? 'flex-1 rounded-md bg-gray-900 py-2.5 text-sm font-medium text-white shadow-sm'
                    : 'flex-1 rounded-md py-2.5 text-sm font-medium text-gray-600 hover:text-gray-900'
                }
              >
                Stratum V1
              </button>
              <button
                type="button"
                onClick={() => setProtocol('v2')}
                className={
                  protocol === 'v2'
                    ? 'flex-1 rounded-md bg-gray-900 py-2.5 text-sm font-medium text-white shadow-sm'
                    : 'flex-1 rounded-md py-2.5 text-sm font-medium text-gray-600 hover:text-gray-900'
                }
              >
                Stratum V2
              </button>
            </div>
            <p className="text-xs text-gray-500">Please keep in mind that V2 is a latest version of the mining protocol and it is recommended to use it for the best performance.</p>
          </div>

          <div className="space-y-3">
            <h3 className="text-base font-semibold text-gray-900">Configure your mining device</h3>

            <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-100 px-3 py-2.5">
              <code className="min-w-0 flex-1 break-all font-mono text-xs text-gray-800 sm:text-sm">{urlLine}</code>
              <button
                type="button"
                onClick={copyUrl}
                className="flex-shrink-0 rounded-md p-2 text-gray-600 hover:bg-gray-200 hover:text-gray-900"
                aria-label="Copy URL"
                title="Copy URL"
              >
                <FiCopy className="h-4 w-4" />
              </button>
            </div>
            {copied && <p className="text-xs text-emerald-600">Copied to clipboard.</p>}

            <div className="rounded-lg border border-gray-200 bg-gray-100 px-3 py-3 font-mono text-xs text-gray-800 sm:text-sm space-y-2">
              <div>
                <span className="text-gray-600">userID: </span>
                <span>{loginId}</span>
                <span className="text-red-600 font-medium">.workerName</span>
              </div>
              <div>
                <span className="text-gray-600">password: </span>
                <span>anything123</span>
              </div>
            </div>

            <div className="space-y-3 text-xs leading-relaxed text-gray-600">
              <p>
                <span className="font-medium text-gray-700">Note:</span> workerName is optional — it is fine if you do
                not provide any. In this case, our system will automatically create an auto worker for you. However, we
                recommend connecting each mining device with a separate workerName for efficient monitoring.
              </p>
              <p>Please be patient. It may take a few minutes for your newly connected device to show up.</p>
            </div>
          </div>
        </div>

        <div className="border-t border-gray-200 px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-indigo-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          >
            Connected! Go back
          </button>
        </div>
      </div>
    </div>
  )

  return typeof document !== 'undefined' ? createPortal(modal, document.body) : null
}
