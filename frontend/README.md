# AlphaCent Trading Platform - Frontend

React + TypeScript frontend for the AlphaCent autonomous trading platform.

## Tech Stack

- **React 19** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **Tailwind CSS v4** - Styling
- **React Router** - Navigation
- **Axios** - HTTP client

## Project Structure

```
frontend/
├── src/
│   ├── components/     # Reusable UI components
│   ├── pages/          # Page components (Login, Dashboard, Settings)
│   ├── hooks/          # Custom React hooks
│   ├── services/       # API client and WebSocket management
│   ├── types/          # TypeScript type definitions
│   ├── utils/          # Utility functions
│   ├── App.tsx         # Main app component with routing
│   ├── main.tsx        # Entry point
│   └── index.css       # Global styles with Tailwind
├── public/             # Static assets
└── package.json        # Dependencies and scripts
```

## Development

### Prerequisites

- Node.js 18+ and npm
- Backend service running on localhost:8000

### Install Dependencies

```bash
npm install
```

### Run Development Server

```bash
npm run dev
```

The app will be available at http://localhost:5173

### Build for Production

```bash
npm run build
```

### Preview Production Build

```bash
npm run preview
```

## Features

- **Authentication** - Secure login with session management
- **Dashboard** - Real-time portfolio monitoring
- **Strategy Management** - Create, backtest, and manage trading strategies
- **Risk Controls** - Kill switch, circuit breakers, position limits
- **Market Data** - Real-time quotes and social insights
- **Settings** - Configure API credentials and risk parameters

## Implementation Status

- [x] Task 19.1: Project initialization with TypeScript, Tailwind CSS, and React Router
- [ ] Task 19.2: Authentication UI
- [ ] Task 19.3: API service layer
- [ ] Task 19.4: Dashboard layout
- [ ] Task 19.5-19.16: Additional components and features

## Notes

- The frontend communicates with the backend via REST API and WebSocket
- All data is stored locally on the user's machine
- The backend continues running strategies even when the browser is closed
