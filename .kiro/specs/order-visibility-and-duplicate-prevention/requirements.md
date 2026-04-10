# Order Visibility and Duplicate Prevention - Requirements

## Problem Statement

Two related issues have been identified:
1. Orders created during autonomous trading cycles may not be visible in the frontend Orders page
2. The system needs better verification to prevent creating duplicate orders for the same asset, especially for crypto vs other asset types

## User Stories

### 1. Order Visibility
**As a** trader  
**I want** to see all orders created by the system in the frontend Orders page  
**So that** I can monitor all trading activity regardless of asset type

### 2. Duplicate Order Prevention
**As a** trader  
**I want** the system to prevent duplicate orders for the same asset  
**So that** I don't accidentally over-expose my portfolio to a single asset

## Acceptance Criteria

### 1.1 All Orders Visible in Frontend
- All orders in the database must be displayed in the frontend Orders page
- No filtering should exclude orders based on asset type (stocks, ETFs, crypto, forex)
- Orders should be sorted by submission time (most recent first)
- The frontend should handle all symbol formats (BTC, BTCUSD, etc.)

### 1.2 Crypto Orde