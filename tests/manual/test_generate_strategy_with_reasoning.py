#!/usr/bin/env python3
"""Generate a test strategy with reasoning to see in the UI."""

import requests
import json

# API endpoint
url = "http://localhost:8000/api/strategies/generate"

# Request payload
payload = {
    "prompt": "Create a momentum strategy that buys stocks showing strong upward price trends over 20 days with high volume confirmation and sells when momentum weakens",
    "constraints": {
        "symbols": ["AAPL", "GOOGL", "MSFT"],
        "timeframe": "1d",
        "risk_tolerance": "medium"
    }
}

# Headers
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer demo_token"
}

print("Generating strategy with reasoning...")
print(f"Prompt: {payload['prompt']}")
print(f"Symbols: {payload['constraints']['symbols']}")
print("\nCalling API...")

try:
    response = requests.post(url, json=payload, headers=headers, timeout=120)
    
    if response.status_code == 200:
        strategy = response.json()
        print("\n✓ Strategy generated successfully!")
        print(f"\nStrategy ID: {strategy['id']}")
        print(f"Name: {strategy['name']}")
        print(f"Status: {strategy['status']}")
        print(f"Description: {strategy['description']}")
        
        if strategy.get('reasoning'):
            print("\n✓ Reasoning captured!")
            reasoning = strategy['reasoning']
            print(f"  Hypothesis: {reasoning.get('hypothesis', 'N/A')[:100]}...")
            print(f"  Alpha Sources: {len(reasoning.get('alpha_sources', []))} sources")
            print(f"  Market Assumptions: {len(reasoning.get('market_assumptions', []))} assumptions")
            print(f"  Signal Logic: {reasoning.get('signal_logic', 'N/A')[:100]}...")
        else:
            print("\n⚠ No reasoning data captured")
        
        print(f"\n🌐 View in UI: http://localhost:5173")
        print("   Navigate to Strategies page and click 'View Reasoning' button")
        
    else:
        print(f"\n✗ Error: {response.status_code}")
        print(response.text)
        
except requests.exceptions.Timeout:
    print("\n✗ Request timed out (LLM generation can take 30-60 seconds)")
except Exception as e:
    print(f"\n✗ Error: {e}")
