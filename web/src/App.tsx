import { useEffect, useState } from 'react'

type ApiStatus = 'checking' | 'connected' | 'unreachable'

const STATUS_TEXT: Record<ApiStatus, string> = {
  checking: 'Checking API…',
  connected: 'API connected',
  unreachable: 'API unreachable',
}

async function checkApi(): Promise<ApiStatus> {
  try {
    const response = await fetch('/healthz')
    return response.ok ? 'connected' : 'unreachable'
  } catch {
    return 'unreachable'
  }
}

function App() {
  const [status, setStatus] = useState<ApiStatus>('checking')

  useEffect(() => {
    let ignore = false
    checkApi().then((result) => {
      if (!ignore) setStatus(result)
    })
    return () => {
      ignore = true
    }
  }, [])

  return (
    <main>
      <h1>Fantasy Agent</h1>
      <p>{STATUS_TEXT[status]}</p>
    </main>
  )
}

export default App
