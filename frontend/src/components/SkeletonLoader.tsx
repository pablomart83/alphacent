import { type FC } from 'react';

interface SkeletonProps {
  className?: string;
}

export const Skeleton: FC<SkeletonProps> = ({ className = '' }) => {
  return (
    <div
      className={`bg-gray-700 rounded animate-pulse ${className}`}
      aria-hidden="true"
    />
  );
};

export const SkeletonTable: FC<{ rows?: number; columns?: number }> = ({
  rows = 3,
  columns = 5,
}) => {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-dark-border">
            {[...Array(columns)].map((_, i) => (
              <th key={i} className="py-3 px-4">
                <Skeleton className="h-3 w-20" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...Array(rows)].map((_, rowIndex) => (
            <tr key={rowIndex} className="border-b border-dark-border">
              {[...Array(columns)].map((_, colIndex) => (
                <td key={colIndex} className="py-4 px-4">
                  <Skeleton className="h-4 w-24" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export const SkeletonCard: FC = () => {
  return (
    <div className="bg-dark-bg rounded-lg p-4 border border-dark-border">
      <Skeleton className="h-3 w-20 mb-2" />
      <Skeleton className="h-6 w-24" />
    </div>
  );
};

export const SkeletonCardGrid: FC<{ count?: number }> = ({ count = 5 }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
      {[...Array(count)].map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
};

export const SkeletonList: FC<{ items?: number }> = ({ items = 3 }) => {
  return (
    <div className="space-y-3">
      {[...Array(items)].map((_, i) => (
        <div key={i} className="bg-dark-bg rounded-lg p-4 border border-dark-border">
          <Skeleton className="h-4 w-1/4 mb-2" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      ))}
    </div>
  );
};

interface ShimmerCardProps {
  title?: string;
  className?: string;
}

export const ShimmerCard: FC<ShimmerCardProps> = ({ title, className = '' }) => {
  return (
    <div className={`bg-dark-bg rounded-lg p-4 border border-dark-border relative overflow-hidden ${className}`}>
      {title && (
        <div className="mb-2">
          <Skeleton className="h-3 w-20" />
        </div>
      )}
      <Skeleton className="h-6 w-24" />
      
      {/* Shimmer effect */}
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/5 to-transparent" />
    </div>
  );
};

interface ShimmerTableProps {
  rows?: number;
  columns?: number;
}

export const ShimmerTable: FC<ShimmerTableProps> = ({ rows = 3, columns = 5 }) => {
  return (
    <div className="overflow-x-auto relative">
      <SkeletonTable rows={rows} columns={columns} />
      
      {/* Shimmer effect overlay */}
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/5 to-transparent pointer-events-none" />
    </div>
  );
};
