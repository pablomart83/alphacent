#!/usr/bin/env python3
"""
Fix risk configuration to prevent over-allocation.
"""
import sqlite3

def fix_risk_config():
    conn = sqlite3.connect('alphacent.db')
    cursor = conn.cursor()
    
    # Check if risk config exists
    cursor.execute("SELECT COUNT(*) FROM risk_config WHERE mode = 'DEMO'")
    exists = cursor.fetchone()[0] > 0
    
    # More conservative risk parameters
    risk_params = {
        'mode': 'DEMO',
        'max_position_size_pct': 0.05,  # 5% max per position (was 20%)
        'max_exposure_pct': 0.50,  # 50% max total exposure (was 90%)
        'max_daily_loss_pct': 0.03,  # 3% daily loss limit
        'max_drawdown_pct': 0.10,  # 10% max drawdown
        'stop_loss_pct': 0.02,  # 2% stop loss
        'take_profit_pct': 0.05,  # 5% take profit
        'position_risk_pct': 0.01,  # 1% risk per position
    }
    
    if exists:
        # Update existing
        cursor.execute("""
            UPDATE risk_config 
            SET max_position_size_pct = ?,
                max_exposure_pct = ?,
                max_daily_loss_pct = ?,
                max_drawdown_pct = ?,
                stop_loss_pct = ?,
                take_profit_pct = ?,
                position_risk_pct = ?
            WHERE mode = 'DEMO'
        """, (
            risk_params['max_position_size_pct'],
            risk_params['max_exposure_pct'],
            risk_params['max_daily_loss_pct'],
            risk_params['max_drawdown_pct'],
            risk_params['stop_loss_pct'],
            risk_params['take_profit_pct'],
            risk_params['position_risk_pct']
        ))
        print("✓ Updated existing risk config")
    else:
        # Insert new
        cursor.execute("""
            INSERT INTO risk_config (
                mode, max_position_size_pct, max_exposure_pct, max_daily_loss_pct,
                max_drawdown_pct, stop_loss_pct, take_profit_pct, position_risk_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            risk_params['mode'],
            risk_params['max_position_size_pct'],
            risk_params['max_exposure_pct'],
            risk_params['max_daily_loss_pct'],
            risk_params['max_drawdown_pct'],
            risk_params['stop_loss_pct'],
            risk_params['take_profit_pct'],
            risk_params['position_risk_pct']
        ))
        print("✓ Created new risk config")
    
    conn.commit()
    conn.close()
    
    print("\n✓ Risk configuration updated:")
    print(f"  - Max position size: {risk_params['max_position_size_pct']:.1%}")
    print(f"  - Max total exposure: {risk_params['max_exposure_pct']:.1%}")
    print(f"  - Max daily loss: {risk_params['max_daily_loss_pct']:.1%}")
    print(f"  - Max drawdown: {risk_params['max_drawdown_pct']:.1%}")
    print("\nThis will prevent over-allocation and balance exhaustion.")

if __name__ == "__main__":
    fix_risk_config()
