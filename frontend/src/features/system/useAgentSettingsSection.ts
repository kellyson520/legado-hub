import { isAxiosError } from 'axios'
import { useEffect, useState } from 'react'

import {
  getSettingsSection,
  saveSettingsSection,
  type SettingsSection,
} from '@/api/modules/system'

export function useAgentSettingsSection<T extends Record<string, unknown>>(tab: string, defaults: T) {
  const [value, setValue] = useState<T>(defaults)
  const [version, setVersion] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [conflict, setConflict] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    void getSettingsSection('agents', tab)
      .then((response) => {
        if (!active) return
        const section = response.data as SettingsSection<T>
        setValue(section.value)
        setVersion(section.version)
        setUpdatedAt(section.updatedAt ?? section.updated_at ?? null)
        setError(null)
      })
      .catch(() => {
        if (active) setError('Failed to load this Agent settings section')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [tab])

  async function save() {
    setSaving(true)
    setError(null)
    setConflict(false)
    try {
      const response = await saveSettingsSection('agents', tab, value, version)
      const section = response.data as SettingsSection<T>
      setValue(section.value)
      setVersion(section.version)
      setUpdatedAt(section.updatedAt ?? section.updated_at ?? null)
      return section
    } catch (saveError) {
      const stale = isAxiosError(saveError) && saveError.response?.status === 409
      setConflict(stale)
      setError(stale ? 'This section changed elsewhere. Your edits are still here; reload before saving again.' : 'Failed to save this Agent settings section')
      return null
    } finally {
      setSaving(false)
    }
  }

  function patch(next: Partial<T>) {
    setValue((current) => ({ ...current, ...next }))
  }

  return { value, patch, loading, saving, error, conflict, updatedAt, save }
}
