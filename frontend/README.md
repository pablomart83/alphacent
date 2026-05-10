# AlphaCent Frontend v2

Greenfield rebuild of the AlphaCent trading dashboard. See `../FRONTEND_REBUILD_SPEC.md` for the full specification.

## Information architecture (5 surfaces)

| Surface | Route | Purpose |
|---|---|---|
| Command | `/` | Is the machine making money right now, and what just happened? |
| Book | `/book` | Positions, orders, execution quality, live account |
| Strategies | `/strategies` | Library, cycle, templates, symbols, graduation, lab |
| Guard | `/guard` | Risk, gates, system health, circuit breakers, alerts, audit |
| Research | `/research` | Deep analytics — performance, attribution, regime, tear sheet |
| Settings | `/settings` | Configuration (off-nav) |

## Stack

React 19 · TypeScript 5.9 · Vite 6 · Tailwind 4 · Radix primitives · TanStack Query + Table + Virtual · Zustand · TradingView Lightweight Charts · Recharts · Visx · JetBrains Mono + Inter · Framer Motion · Sonner · Lucide.

## Development

```bash
npm install
npm run dev        # Vite dev server on :5173, proxies /api + /ws to :8000
npm run typecheck  # Strict TS check
npm run build      # Typecheck + Vite build -> dist/
npm run lint
```

## Deployment

Nginx serves `dist/` at `https://alphacent.co.uk`. Build locally with production env:

```bash
VITE_API_BASE_URL=https://alphacent.co.uk \
VITE_WS_BASE_URL=wss://alphacent.co.uk \
npm run build

scp -i ~/Downloads/alphacent-key.pem -r dist/* ubuntu@34.252.61.149:/home/ubuntu/alphacent/frontend/dist/
```

Instant rollback: swap `frontend/` and `frontend_v1_backup/` on EC2.
