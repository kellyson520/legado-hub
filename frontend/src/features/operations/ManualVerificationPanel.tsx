import { useEffect, useRef, useState } from 'react'
import RFB from '@novnc/novnc'

import { useLanguage } from '@/app/providers/LanguageProvider'
import {
  cancelInteractiveBrowserSession,
  continueInteractiveBrowserSession,
  createInteractiveBrowserRelayTicket,
  getInteractiveBrowserSession,
  type InteractiveBrowserSession,
} from '@/api/modules/interactiveBrowser'
import { Button } from '@/components/ui/button'

function relayUrl(path: string) {
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${window.location.host}${path}`
}

export function ManualVerificationPanel({ sessionId, onFinished }: { sessionId: string; onFinished: () => void }) {
  const { t } = useLanguage()
  const [session, setSession] = useState<InteractiveBrowserSession | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const screenRef = useRef<HTMLDivElement>(null)
  const rfbRef = useRef<RFB | null>(null)

  useEffect(() => {
    let active = true
    async function open() {
      try {
        const [sessionResponse, ticketResponse] = await Promise.all([
          getInteractiveBrowserSession(sessionId),
          createInteractiveBrowserRelayTicket(sessionId),
        ])
        if (!active) return
        setSession(sessionResponse.data)
        if (screenRef.current) rfbRef.current = new RFB(screenRef.current, relayUrl(ticketResponse.data.relay_path))
      } catch {
        if (active) setMessage('Unable to open the manual verification session')
      }
    }
    void open()
    return () => {
      active = false
      rfbRef.current?.disconnect()
      rfbRef.current = null
    }
  }, [sessionId])

  async function continueValidation() {
    setBusy(true)
    setMessage(null)
    try {
      const response = await continueInteractiveBrowserSession(sessionId)
      setMessage(response.data.validation.passed ? 'Validation passed' : response.data.validation.reason || 'Validation failed')
      if (response.data.validation.passed) onFinished()
    } catch {
      setMessage('Unable to continue validation')
    } finally {
      setBusy(false)
    }
  }

  async function cancel() {
    setBusy(true)
    try {
      await cancelInteractiveBrowserSession(sessionId)
      onFinished()
    } catch {
      setMessage('Unable to cancel the verification session')
    } finally {
      setBusy(false)
    }
  }

  const host = session?.target_origin ? new URL(session.target_origin).host : 'Loading target host…'
  return (
    <section className="space-y-3 rounded-xl border border-border bg-card p-4" aria-label={t('Manual verification session')}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-medium text-foreground">{t('Manual verification')}</h3>
          <p className="text-sm text-muted-foreground">{t('Only complete verification for sites you are authorised to access: ')}{host}</p>
        </div>
        <span className="text-xs text-muted-foreground">{t(session?.state ?? 'opening')}</span>
      </div>
      <div ref={screenRef} className="min-h-72 rounded-md bg-muted" />
      {message ? <p role="status" className="text-sm text-muted-foreground">{t(message)}</p> : null}
      <div className="flex flex-wrap gap-2">
        <Button onClick={continueValidation} disabled={busy}>{t('Continue validation')}</Button>
        <Button variant="outline" onClick={cancel} disabled={busy}>{t('Cancel and destroy session')}</Button>
      </div>
    </section>
  )
}
