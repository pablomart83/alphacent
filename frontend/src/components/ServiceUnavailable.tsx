import { type FC } from 'react';

interface ServiceUnavailableProps {
  serviceName: string;
  message?: string;
  impact?: string;
  onRetry?: () => void | Promise<void>;
  className?: string;
}

export const ServiceUnavailable: FC<ServiceUnavailableProps> = ({
  serviceName,
  message,
  impact,
  onRetry,
  className = '',
}) => {
  return (
    <div
      className={`bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 ${className}`}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 text-yellow-500 text-lg">⚠️</div>
        <div className="flex-1">
          <h3 className="text-yellow-400 text-sm font-mono font-semibold mb-1">
            {serviceName} Unavailable
          </h3>
          {message && (
            <p className="text-yellow-400/80 text-xs font-mono mb-2">{message}</p>
          )}
          {impact && (
            <p className="text-gray-400 text-xs font-mono mb-3">
              Impact: {impact}
            </p>
          )}
          {onRetry && (
            <button
              onClick={onRetry}
              className="px-3 py-1 text-xs font-mono bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 rounded hover:bg-yellow-500/30 transition-colors"
            >
              ↻ Retry Connection
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

interface DegradedModeProps {
  features: string[];
  reason: string;
  className?: string;
}

export const DegradedMode: FC<DegradedModeProps> = ({
  features,
  reason,
  className = '',
}) => {
  return (
    <div
      className={`bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 ${className}`}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 text-yellow-500 text-lg">⚡</div>
        <div className="flex-1">
          <h3 className="text-yellow-400 text-sm font-mono font-semibold mb-1">
            Running in Degraded Mode
          </h3>
          <p className="text-yellow-400/80 text-xs font-mono mb-2">{reason}</p>
          <div className="mt-2">
            <p className="text-gray-400 text-xs font-mono mb-1">
              Limited features:
            </p>
            <ul className="list-disc list-inside text-gray-400 text-xs font-mono space-y-1">
              {features.map((feature, index) => (
                <li key={index}>{feature}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};
