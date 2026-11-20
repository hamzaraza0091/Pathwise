import { useCallback, useEffect, useRef, useState } from 'react'
import api, { errorMessage } from './api'

export function useFetch(path, params, { enabled = true } = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState('')
  const key = JSON.stringify([path, params])
  const counter = useRef(0)

  const load = useCallback(async () => {
    if (!enabled || !path) return
    const id = ++counter.current
    setLoading(true)
    setError('')
    try {
      const response = await api.get(path, { params })
      if (id === counter.current) setData(response.data)
    } catch (err) {
      if (id === counter.current) setError(errorMessage(err))
    } finally {
      if (id === counter.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled])

  useEffect(() => {
    load()
  }, [load])

  return { data, loading, error, reload: load, setData }
}

export function useAction() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const run = useCallback(async (fn) => {
    setBusy(true)
    setError('')
    try {
      return await fn()
    } catch (err) {
      setError(errorMessage(err))
      return undefined
    } finally {
      setBusy(false)
    }
  }, [])
  return { busy, error, run, setError }
}

export function useDebounced(value, delay = 250) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}
