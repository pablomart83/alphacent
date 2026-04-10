# How to View the StrategyReasoningPanel with Real Data

## Current Status
✅ StrategyReasoningPanel component created and integrated
✅ Frontend dev server running at http://localhost:5173
✅ Backend API running at http://localhost:8000

## Steps to See the Panel

### Step 1: Login to Get Auth Token
1. Open http://localhost:5173 in your browser
2. Login with:
   - Username: `admin`
   - Password: `admin123`

### Step 2: Navigate to Strategies Page
1. Click on "Strategies" in the sidebar
2. You should see existing strategies listed

### Step 3: Generate a New Strategy with Reasoning
1. Click the "+ Generate Strategy" button
2. Enter a prompt like:
   ```
   Create a momentum strategy that buys stocks showing strong upward price trends over 20 days with high volume confirmation and sells when momentum weakens
   ```
3. Add symbols: `AAPL, GOOGL, MSFT`
4. Select timeframe: `1d`
5. Select risk tolerance: `medium`
6. Click "Generate Strategy"
7. Wait 30-60 seconds for the LLM to generate the strategy

### Step 4: View the Reasoning Panel
1. Once the strategy is generated, you'll see it in the list
2. Look for the "▶ View Reasoning" button on the strategy card
3. Click it to expand the StrategyReasoningPanel
4. You'll see:
   - **Hypothesis**: The core market belief
   - **Market Assumptions**: List of assumptions
   - **Alpha Sources**: Visual bars showing sources of edge with weights
   - **Signal Logic**: How signals are generated
   - **Expand button**: Click to see confidence factors, LLM prompt, and raw response

## What You'll See in the Panel

### Main View (Always Visible)
- **Hypothesis**: "Stocks with strong upward momentum over 20 days tend to continue..."
- **Market Assumptions**: Bulleted list of market beliefs
- **Alpha Sources**: Color-coded bars showing:
  - Momentum (blue) - 60%
  - Volume (orange) - 30%
  - Volatility (yellow) - 10%
- **Signal Logic**: Explanation of entry/exit conditions

### Expanded View (Click "▶ Expand")
- **Confidence Factors**: Progress bars for trend_strength, volume_confirmation, etc.
- **Original Prompt**: Your input text
- **LLM Response**: Raw JSON response from the LLM

## Troubleshooting

### If you don't see the "View Reasoning" button:
- The strategy doesn't have reasoning data
- Generate a new strategy using the steps above

### If strategy generation fails:
- Check that Ollama is running: `ollama list`
- Check backend logs in the terminal
- The LLM might take 30-60 seconds to respond

### If you see "No auth token" errors:
- Make sure you're logged in
- Refresh the page after logging in

## Alternative: Use Existing Strategy with Mock Data

If you want to see the panel immediately without waiting for LLM generation, I can add mock reasoning data to an existing strategy in the database.

Would you like me to:
1. Add mock reasoning data to an existing strategy? (Quick)
2. Wait for you to generate a real strategy? (Takes 30-60 seconds)
3. Both?

## Current Implementation

The StrategyReasoningPanel is now:
- ✅ Created in `frontend/src/components/StrategyReasoningPanel.tsx`
- ✅ Integrated into `frontend/src/components/Strategies.tsx`
- ✅ Displays hypothesis, assumptions, alpha sources, and signal logic
- ✅ Has expandable section for full details
- ✅ Uses real data from the API
- ✅ Connected to WebSocket for live updates
- ✅ Styled consistently with the rest of the UI

## Next Steps

Once you see the panel working:
1. Try expanding/collapsing it
2. Generate multiple strategies to compare reasoning
3. Check how alpha sources are visualized with different weights
4. View the confidence factors in the expanded section
