# How to Enter Your eToro API Credentials

## Current Situation

The credentials file contains a CORS error message instead of actual API keys. This happened because the credentials were never properly saved through the UI.

## Option 1: Use Python Script (Recommended)

I've created a script to save your credentials directly:

```bash
# Activate virtual environment
source venv/bin/activate

# Run the credentials script
python3 save_credentials.py
```

The script will prompt you for:
1. Trading Mode (DEMO or LIVE)
2. Public API Key (x-api-key)
3. User Key (x-user-key)

Your credentials will be encrypted and saved to `config/demo_credentials.json` or `config/live_credentials.json`.

## Option 2: Use the Frontend UI

1. **Start the backend** (if not already running):
   ```bash
   source venv/bin/activate
   python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000
   ```

2. **Start the frontend** (in a new terminal):
   ```bash
   cd frontend
   npm run dev
   ```

3. **Open the browser**:
   - Navigate to `http://localhost:5173`
   - Login with: username=`admin`, password=`admin123`

4. **Go to Settings**:
   - Click "Settings" in the sidebar
   - Find the "API Configuration" section

5. **Enter your credentials**:
   - eToro Public Key: `[your x-api-key]`
   - eToro User Key: `[your x-user-key]`
   - Click "Save Credentials"

## Option 3: Manual API Call

```bash
# Login first
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  -c cookies.txt

# Save credentials
curl -X POST http://localhost:8000/config/credentials \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "mode": "DEMO",
    "public_key": "YOUR_PUBLIC_KEY_HERE",
    "user_key": "YOUR_USER_KEY_HERE"
  }'
```

## Where to Get Your eToro API Keys

1. Log in to your eToro account
2. Go to **Settings** > **Trading**
3. Scroll to **API Key Management**
4. Click **Create New Key**
5. Configure:
   - **Key Name**: AlphaCent (or any name)
   - **Permissions**: Read + Write (for trading)
   - **Security**: Optional IP whitelist/expiration
6. Click **Generate Key**
7. **Verify your identity** (SMS/phone call)
8. **Copy both keys**:
   - Public API Key (x-api-key)
   - User Key (x-user-key)

## Important Notes

### Key Format
- **Public Key**: Usually 50-100 characters
- **User Key**: Usually 50-100 characters (NOT 2832 characters like the current error)

### Security
- Keys are encrypted before storage using Fernet encryption
- Encryption key is stored in `config/.encryption_key`
- Never commit credentials to version control
- Use separate keys for Demo and Live modes

### Testing After Saving

Once you've saved your credentials, test them:

```bash
source venv/bin/activate
python3 test_etoro_api.py
```

This will test:
- ✅ Credentials loading
- ✅ API authentication
- ✅ Market data retrieval

## What Happens Next

Once you enter valid credentials:

1. **Market Data** will work:
   - Real-time prices from eToro
   - Historical candle data
   - Instrument information

2. **Account Data** may work (if endpoints are available):
   - Account balance
   - Positions
   - Order history

3. **Trading** will work (with Write permissions):
   - Place orders
   - Cancel orders
   - Close positions

## Current Workaround

Until you enter valid credentials, the system uses:
- **Public eToro endpoints** (no auth required) for market data
- **Database cache** for account/position data
- **Mock data** as final fallback

This means market data already works without credentials!

## Ready to Enter Credentials?

Choose your preferred method above and enter your eToro API keys. I'm ready to help test the integration once you've saved them!

