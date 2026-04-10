# AlphaCent Development Startup Guide

This guide shows you how to start both the backend and frontend servers together.

## Quick Start (Recommended)

### Option 1: Using npm (Cross-platform)

Simply run:

```bash
npm run dev
```

This will start both servers simultaneously with colored output:
- **Backend** (blue): http://localhost:8000
- **Frontend** (green): http://localhost:5173

Press `Ctrl+C` to stop both servers.

### Option 2: Using Shell Script (macOS/Linux)

```bash
./start-dev.sh
```

This script:
- ✅ Checks for virtual environment
- ✅ Checks for node_modules
- ✅ Starts backend on port 8000
- ✅ Starts frontend on port 5173
- ✅ Shows colored status messages
- ✅ Tails logs from both servers
- ✅ Gracefully shuts down both on Ctrl+C

## Manual Start (If you prefer separate terminals)

### Terminal 1 - Backend:
```bash
source venv/bin/activate
python run_backend.py
```

### Terminal 2 - Frontend:
```bash
cd frontend
npm run dev
```

## Troubleshooting

### Backend won't start
- Check if virtual environment exists: `ls venv/`
- Check if dependencies installed: `pip list`
- Check logs: `tail -f backend.log`

### Frontend won't start
- Check if node_modules exists: `ls frontend/node_modules/`
- Install dependencies: `cd frontend && npm install`
- Check logs: `tail -f frontend.log`

### Port already in use
- Backend (8000): `lsof -ti:8000 | xargs kill -9`
- Frontend (5173): `lsof -ti:5173 | xargs kill -9`

## What's Running?

After successful startup:

| Service  | URL                      | Purpose                          |
|----------|--------------------------|----------------------------------|
| Backend  | http://localhost:8000    | API, WebSocket, Trading Engine   |
| Frontend | http://localhost:5173    | React UI                         |

## Logs

Both startup methods create log files:
- `backend.log` - Backend server logs
- `frontend.log` - Frontend dev server logs

View logs in real-time:
```bash
tail -f backend.log frontend.log
```

## Stopping Servers

### If using npm or shell script:
Press `Ctrl+C` - both servers will stop gracefully

### If running manually:
Press `Ctrl+C` in each terminal window

### Force kill if needed:
```bash
# Kill backend
pkill -f "python run_backend.py"

# Kill frontend
pkill -f "vite"
```

## First Time Setup

If this is your first time running the project:

1. **Create virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Install frontend dependencies:**
   ```bash
   cd frontend
   npm install
   cd ..
   ```

3. **Install root dependencies (for npm scripts):**
   ```bash
   npm install
   ```

4. **Start development:**
   ```bash
   npm run dev
   ```

## Available npm Scripts

From the root directory:

- `npm run dev` - Start both backend and frontend
- `npm run dev:backend` - Start only backend
- `npm run dev:frontend` - Start only frontend
- `npm start` - Alias for `npm run dev`

## Tips

- The backend status is shown in the Settings page of the frontend
- WebSocket connection status is shown in the UI
- Check the browser console for frontend errors
- Check backend.log for API errors
