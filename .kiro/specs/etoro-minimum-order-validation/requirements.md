# Requirements Document

## Introduction

This feature implements validation for eToro's minimum order size requirements to prevent order submission failures. Currently, orders with amounts below eToro's $10 minimum are being submitted and subsequently rejected by the eToro API with error code 720. 

The root cause is that eToro's API expects order amounts in **dollars** (account currency), not in shares/units. When users specify quantities (like "buy 1 share"), the system is incorrectly passing this as $1 instead of calculating the dollar value based on the current market price. This validation will:
1. Ensure order amounts are properly calculated in dollars before submission
2. Validate that the dollar amount meets eToro's $10 minimum
3. Provide clear feedback when orders don't meet requirements

## Glossary

- **Order_Validator**: Component responsible for validating order parameters before submission
- **eToro_Client**: API client that communicates with eToro's trading platform
- **Order_Monitor**: Background service that processes pending orders
- **Order_API**: REST API endpoint for order creation
- **Minimum_Order_Amount**: The minimum dollar amount required for an order ($10 for eToro)
- **Leveraged_Amount**: The actual position size after applying leverage (for eToro, this equals Amount × Leverage)
- **Order_Amount**: The dollar value of an order in account currency (USD for eToro)
- **Quantity**: The number of shares/units being ordered
- **Market_Price**: The current trading price of an instrument

## Requirements

### Requirement 1: Pre-Submission Order Validation

**User Story:** As a trader, I want my orders to be validated before submission to eToro, so that I receive immediate feedback about invalid orders instead of waiting for API failures.

#### Acceptance Criteria

1. WHEN an order is created through the API, THE Order_API SHALL validate the order amount before processing
2. WHEN an order is processed by the monitor, THE Order_Monitor SHALL validate the order amount before submission to eToro
3. WHEN an order is submitted directly through the client, THE eToro_Client SHALL validate the order amount before making the API call
4. THE Order_Validator SHALL check that the leveraged amount meets or exceeds the Minimum_Order_Amount
5. WHEN validation fails, THE system SHALL prevent the order from being submitted to eToro

### Requirement 2: Minimum Amount Enforcement

**User Story:** As a system administrator, I want to enforce eToro's $10 minimum order requirement, so that orders are not rejected by the eToro API.

#### Acceptance Criteria

1. THE Order_Validator SHALL reject orders where the leveraged amount is less than $10
2. WHEN calculating the leveraged amount, THE Order_Validator SHALL multiply the order amount by the leverage value
3. WHERE leverage is not specified, THE Order_Validator SHALL assume a leverage of 1
4. THE Order_Validator SHALL use the exact minimum amount value required by eToro ($10)
5. WHEN the leveraged amount equals exactly $10, THE Order_Validator SHALL accept the order

### Requirement 3: Clear Error Messaging

**User Story:** As a trader, I want to receive clear error messages when my order is rejected, so that I understand what went wrong and how to fix it.

#### Acceptance Criteria

1. WHEN an order fails validation, THE system SHALL return an error message indicating the minimum order requirement
2. THE error message SHALL include the actual order amount that was provided
3. THE error message SHALL include the minimum required amount ($10)
4. WHEN leverage is applied, THE error message SHALL show both the base amount and the leveraged amount
5. THE error message SHALL be consistent across all validation points (API, Monitor, Client)

### Requirement 4: Validation Layer Integration

**User Story:** As a developer, I want validation to be integrated at multiple layers, so that invalid orders are caught regardless of how they enter the system.

#### Acceptance Criteria

1. THE Order_API SHALL validate orders at the REST API endpoint level before creating order records
2. THE Order_Monitor SHALL validate orders before submitting them to eToro
3. THE eToro_Client SHALL validate orders as a final check before making API calls
4. WHEN validation fails at any layer, THE system SHALL update the order status appropriately
5. WHEN validation fails in the Order_Monitor, THE system SHALL mark the order as FAILED with the validation error

### Requirement 5: Configurable Minimum Amounts

**User Story:** As a system administrator, I want minimum order amounts to be configurable, so that the system can adapt to changes in eToro's requirements or support different instruments with different minimums.

#### Acceptance Criteria

1. THE Order_Validator SHALL read the minimum order amount from a configuration source
2. THE system SHALL support a default minimum amount of $10
3. WHERE instrument-specific minimums are defined, THE Order_Validator SHALL use the instrument-specific minimum
4. WHERE no instrument-specific minimum exists, THE Order_Validator SHALL use the default minimum
5. THE configuration SHALL be updatable without code changes

### Requirement 6: Validation Error Handling

**User Story:** As a developer, I want validation errors to be handled consistently, so that the system behavior is predictable and maintainable.

#### Acceptance Criteria

1. WHEN validation fails at the API level, THE system SHALL return an HTTP 400 Bad Request status
2. WHEN validation fails in the Order_Monitor, THE system SHALL log the error and mark the order as FAILED
3. WHEN validation fails in the eToro_Client, THE system SHALL raise a ValueError with the validation error message
4. THE system SHALL NOT submit orders to eToro when validation fails
5. THE system SHALL preserve the original order details when validation fails for audit purposes

### Requirement 7: Backward Compatibility

**User Story:** As a system administrator, I want the validation feature to integrate seamlessly with existing code, so that deployment is smooth and existing functionality is not disrupted.

#### Acceptance Criteria

1. THE Order_Validator SHALL integrate with existing order placement workflows without breaking changes
2. THE system SHALL continue to support all existing order types (MARKET, LIMIT, STOP_LOSS, TAKE_PROFIT)
3. THE system SHALL continue to support all existing order parameters (symbol, side, quantity, price, stop_price)
4. WHEN validation is added, THE system SHALL maintain existing error handling for other validation types
5. THE system SHALL maintain existing logging and monitoring capabilities
