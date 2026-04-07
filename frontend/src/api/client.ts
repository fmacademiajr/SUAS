import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || ''

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// Inject Firebase ID token before every request
// The interceptor calls getIdToken() from a lazy-loaded auth ref
// to avoid circular imports (AuthContext imports apiClient).
let _getIdToken: (() => Promise<string>) | null = null

export function setAuthTokenProvider(fn: () => Promise<string>) {
  _getIdToken = fn
}

apiClient.interceptors.request.use(async (config) => {
  if (_getIdToken) {
    try {
      const token = await _getIdToken()
      config.headers.Authorization = `Bearer ${token}`
    } catch {
      // Token unavailable (e.g. not logged in) — let the request go without auth
      // The backend will return 401, which React Query will surface
    }
  }
  return config
})

// Normalize errors to readable messages
apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'An unexpected error occurred'
    return Promise.reject(new Error(message))
  }
)
