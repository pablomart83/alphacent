/**
 * Error message utilities for user-friendly error handling
 */

export interface ApiError {
  response?: {
    status?: number;
    data?: {
      detail?: string;
      message?: string;
    };
  };
  message?: string;
}

/**
 * Get user-friendly error message from API error
 */
export function getErrorMessage(error: ApiError | any): string {
  // Handle axios error response
  if (error.response) {
    const status = error.response.status;
    const detail = error.response.data?.detail;
    const message = error.response.data?.message;
    
    // Use backend error message if available
    if (detail) return detail;
    if (message) return message;
    
    // Map status codes to user-friendly messages
    switch (status) {
      case 400:
        return 'Invalid request. Please check your input and try again.';
      case 401:
        return 'Session expired. Please log in again.';
      case 403:
        return 'You don\'t have permission to perform this action.';
      case 404:
        return 'Resource not found.';
      case 422:
        return 'Invalid data. Please check your input.';
      case 429:
        return 'Too many requests. Please wait a moment and try again.';
      case 500:
        return 'Server error. Please try again later.';
      case 503:
        return 'Service temporarily unavailable. Please try again.';
      default:
        return `Request failed with status ${status}. Please try again.`;
    }
  }
  
  // Handle network errors
  if (error.message) {
    if (error.message.includes('Network Error')) {
      return 'Network error. Please check your connection and try again.';
    }
    if (error.message.includes('timeout')) {
      return 'Request timed out. Please try again.';
    }
    return error.message;
  }
  
  // Fallback
  return 'An unexpected error occurred. Please try again.';
}

/**
 * Check if error is a network error
 */
export function isNetworkError(error: ApiError | any): boolean {
  return !error.response && error.message?.includes('Network Error');
}

/**
 * Check if error is an authentication error
 */
export function isAuthError(error: ApiError | any): boolean {
  return error.response?.status === 401;
}

/**
 * Check if error is a validation error
 */
export function isValidationError(error: ApiError | any): boolean {
  return error.response?.status === 422 || error.response?.status === 400;
}

/**
 * Check if error is a server error
 */
export function isServerError(error: ApiError | any): boolean {
  const status = error.response?.status;
  return status && status >= 500 && status < 600;
}

/**
 * Get error severity level
 */
export function getErrorSeverity(error: ApiError | any): 'info' | 'warning' | 'error' | 'critical' {
  const status = error.response?.status;
  
  if (!status) return 'error';
  
  if (status === 401 || status === 403) return 'warning';
  if (status >= 500) return 'critical';
  if (status >= 400) return 'error';
  
  return 'info';
}
