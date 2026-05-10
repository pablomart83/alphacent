/**
 * Structured error classification for user-facing error messages.
 * Inspects AxiosError shape to produce contextual, actionable messages.
 */

export interface ClassifiedError {
  title: string;
  message: string;
  isNetwork: boolean;
  isServer: boolean;
  isAuth: boolean;
  retryable: boolean;
}

/**
 * Classify an error into a user-friendly structure.
 *
 * @param error   - The caught error (typically an AxiosError)
 * @param dataName - Human-readable name of the data that failed (e.g. "positions", "risk metrics")
 */
export function classifyError(error: unknown, dataName: string): ClassifiedError {
  const title = `Failed to load ${dataName}`;

  // AxiosError-like shape check
  const axiosErr = error as {
    response?: { status?: number; data?: { detail?: string; message?: string } };
    message?: string;
  } | undefined;

  // No response at all → network error
  if (!axiosErr?.response) {
    return {
      title,
      message: 'Network error — check your connection and try again.',
      isNetwork: true,
      isServer: false,
      isAuth: false,
      retryable: true,
    };
  }

  const status = axiosErr.response.status ?? 0;

  // Auth errors
  if (status === 401 || status === 403) {
    return {
      title,
      message: 'Session expired or unauthorized. Please log in again.',
      isNetwork: false,
      isServer: false,
      isAuth: true,
      retryable: false,
    };
  }

  // Server errors (5xx)
  if (status >= 500) {
    return {
      title,
      message: 'Server error — the backend encountered a problem. Try again shortly.',
      isNetwork: false,
      isServer: true,
      isAuth: false,
      retryable: true,
    };
  }

  // Client errors (4xx)
  if (status >= 400) {
    const detail =
      axiosErr.response.data?.detail ??
      axiosErr.response.data?.message ??
      `Request failed (${status}).`;
    return {
      title,
      message: String(detail),
      isNetwork: false,
      isServer: false,
      isAuth: false,
      retryable: false,
    };
  }

  // Unknown / fallback
  return {
    title,
    message: 'An unexpected error occurred. Please try again.',
    isNetwork: false,
    isServer: false,
    isAuth: false,
    retryable: true,
  };
}
