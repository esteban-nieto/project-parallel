import { useState, useCallback } from 'react'

const TOKEN_KEY = 'pp_token'

export function useAuth() {
  const [token, setTokenState] = useState(
    () => localStorage.getItem(TOKEN_KEY) || ''
  )
  const [loading, setLoading] = useState(false)

  const setToken = useCallback((newToken) => {
    if (newToken) {
      localStorage.setItem(TOKEN_KEY, newToken)
      setTokenState(newToken)
    } else {
      localStorage.removeItem(TOKEN_KEY)
      setTokenState('')
    }
  }, [])

  return { token, setToken, loading, setLoading }
}
