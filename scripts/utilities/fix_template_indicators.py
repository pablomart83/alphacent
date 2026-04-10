"""Fix indicator names in strategy templates."""

import re

# Read the file
with open('src/strategy/strategy_templates.py', 'r') as f:
    content = f.read()

# Define replacements (old pattern -> new pattern)
replacements = [
    # EMA
    (r'required_indicators=\["EMA_20", "EMA_50"\]', 'required_indicators=["EMA:20", "EMA:50"]'),
    
    # ATR + SMA + Price Change
    (r'required_indicators=\["ATR_14", "SMA_20", "PRICE_CHANGE_PCT_1"\]', 'required_indicators=["ATR", "SMA", "Price Change %"]'),
    
    # Bollinger Bands (Upper/Middle/Lower) -> Bollinger Bands
    (r'required_indicators=\["Upper_Band_20", "Middle_Band_20"\]', 'required_indicators=["Bollinger Bands"]'),
    (r'required_indicators=\["Lower_Band_20", "Middle_Band_20", "Upper_Band_20"\]', 'required_indicators=["Bollinger Bands"]'),
    (r'required_indicators=\["Upper_Band_20", "Middle_Band_20", "Lower_Band_20", "ATR_14"\]', 'required_indicators=["Bollinger Bands", "ATR"]'),
    (r'required_indicators=\["Upper_Band_20", "Middle_Band_20", "Lower_Band_20", "VOLUME_MA_20"\]', 'required_indicators=["Bollinger Bands", "Volume MA"]'),
    
    # MACD
    (r'required_indicators=\["MACD_12_26_9", "MACD_12_26_9_SIGNAL"\]', 'required_indicators=["MACD"]'),
    (r'required_indicators=\["MACD_12_26_9", "MACD_12_26_9_SIGNAL", "SMA_50"\]', 'required_indicators=["MACD", "SMA:50"]'),
    
    # ADX + SMA
    (r'required_indicators=\["ADX_14", "SMA_50"\]', 'required_indicators=["ADX", "SMA:50"]'),
    
    # Stochastic
    (r'required_indicators=\["STOCH_14"\]', 'required_indicators=["Stochastic Oscillator"]'),
    
    # SMA only
    (r'required_indicators=\["SMA_20"\]', 'required_indicators=["SMA"]'),
    
    # SMA + ATR
    (r'required_indicators=\["SMA_20", "ATR_14"\]', 'required_indicators=["SMA", "ATR"]'),
    
    # Support/Resistance + Volume MA + SMA
    (r'required_indicators=\["Resistance", "VOLUME_MA_20", "SMA_20"\]', 'required_indicators=["Support/Resistance", "Volume MA", "SMA"]'),
    
    # SMA + RSI (multiple periods)
    (r'required_indicators=\["SMA_20", "SMA_50", "RSI_14"\]', 'required_indicators=["SMA:20", "SMA:50", "RSI"]'),
    
    # RSI + SMA (multiple periods)
    (r'required_indicators=\["RSI_14", "SMA_20", "SMA_50"\]', 'required_indicators=["RSI", "SMA:20", "SMA:50"]'),
    
    # Support + RSI + Stochastic + SMA
    (r'required_indicators=\["Support", "RSI_14", "STOCH_14", "SMA_20"\]', 'required_indicators=["Support/Resistance", "RSI", "Stochastic Oscillator", "SMA"]'),
    
    # RSI only
    (r'required_indicators=\["RSI_14"\]', 'required_indicators=["RSI"]'),
]

# Apply replacements
for old, new in replacements:
    content = re.sub(old, new, content)

# Write back
with open('src/strategy/strategy_templates.py', 'w') as f:
    f.write(content)

print("✓ Fixed all indicator names in templates")
