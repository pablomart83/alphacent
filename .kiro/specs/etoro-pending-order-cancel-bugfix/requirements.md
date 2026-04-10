# Requirements Document: eToro Pending Order Cancellation Bugfix

## Introduction

This document specifies the requirements for fixing a critical bug where pending orders deleted from the frontend interface are removed from the local database but are NOT canceled on the eToro platform. This results in orders remaining active on eToro even though users believe they have been canceled, potentially leading to unexpected trades when markets open.

The bug occurs specifically when orders are in PENDING state (typically outside market hours) and users attempt to cancel them through the frontend UI. While the local database is updated to reflect the cancellation, the eToro API call to cancel the order either fails silently or is not properly executed.

## Glossary

- **Order_Cancellation_System**: The backend system responsible for canceling orders both locally and on eToro
- **eToro_API_Client**: The client that communicates with eToro's trading API
- **Frontend_UI**: The user interface where users can view and cancel pending orders
- **Pending_Order**: An order with status PENDING or SUBMITTED that has not yet been filled
- **Local_Database**: The application's database storing order records
- **eToro_Platform**: The external eToro trading platform where actual orders are placed
- **Order_ID**: The internal application identifier for an order
- **eToro_Order_ID**: The identifier assigned by eToro to track orders on their platform

## Requirements

### Requirement 1: Root Cause Investigation

**User Story:** As a developer, I want to understand why pending order cancellations fail on eToro, so that I can implement an effective fix.

#### Acceptance Criteria

1. WHEN investigating the cancel_order endpoint in orders.py, THE Investigation SHALL identify whether the eToro API call is being executed
2. WHEN investigating the EToroAPIClient.cancel_order method, THE Investigation SHALL verify the correct API endpoint is being used for pending order cancellation
3. WHEN investigating error handling, THE Investigation SHALL determine if cancellation failures are being logged and surfaced to users
4. WHEN investigating the order cancellation flow, THE Investigation SHALL verify that etoro_order_id exists before attempting eToro API cancellation
5. WHEN investigating eToro API responses, THE Investigation SHALL determine if the API returns success=False or throws exceptions for pending orders

### Requirement 2: eToro API Cancellation Reliability

**User Story:** As a user, I want pending order cancellations to reliably cancel orders on eToro, so that I don't have unexpected trades execute.

#### Acceptance Criteria

1. WHEN a user cancels a pending order with a valid etoro_order_id, THE Order_Cancellation_System SHALL call the eToro API to cancel the order
2. WHEN the eToro API cancellation succeeds, THE Order_Cancellation_System SHALL update the local database status to CANCELLED
3. WHEN the eToro API cancellation fails, THE Order_Cancellation_System SHALL NOT update the local database status to CANCELLED
4. WHEN the eToro API cancellation fails, THE Order_Cancellat