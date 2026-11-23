import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

function stubFetch(respond: () => Promise<Response>) {
  const fetch = vi.fn(respond)
  vi.stubGlobal('fetch', fetch)
  return fetch
}

describe('App', () => {
  it('shows the app name', () => {
    stubFetch(() => new Promise(() => {}))

    render(<App />)

    expect(screen.getByRole('heading', { name: 'Fantasy Agent' })).toBeInTheDocument()
  })

  it('reports a healthy API', async () => {
    const fetch = stubFetch(async () => Response.json({ status: 'ok' }))

    render(<App />)

    expect(await screen.findByText('API connected')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith('/healthz')
  })

  it('reports an API that cannot be reached', async () => {
    stubFetch(async () => {
      throw new TypeError('Failed to fetch')
    })

    render(<App />)

    expect(await screen.findByText('API unreachable')).toBeInTheDocument()
  })

  it('reports an API that answers with an error', async () => {
    stubFetch(async () => new Response(null, { status: 502 }))

    render(<App />)

    expect(await screen.findByText('API unreachable')).toBeInTheDocument()
  })
})
