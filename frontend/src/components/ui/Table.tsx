import { type FC, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface TableProps {
  children: ReactNode;
  className?: string;
}

export const Table: FC<TableProps> = ({ children, className = '' }) => {
  return (
    <div className="overflow-x-auto">
      <table className={cn('table w-full', className)}>{children}</table>
    </div>
  );
};

interface TableHeaderProps {
  children: ReactNode;
  className?: string;
}

export const TableHeader: FC<TableHeaderProps> = ({ children, className }) => {
  return <thead className={cn('bg-[var(--color-dark-bg)]', className)}>{children}</thead>;
};

interface TableBodyProps {
  children: ReactNode;
  className?: string;
}

export const TableBody: FC<TableBodyProps> = ({ children, className }) => {
  return <tbody className={className}>{children}</tbody>;
};

interface TableRowProps {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}

export const TableRow: FC<TableRowProps> = ({ children, onClick, className = '' }) => {
  return (
    <tr
      onClick={onClick}
      className={cn(
        'transition-colors even:bg-[var(--color-table-alt-row)]',
        onClick && 'cursor-pointer hover:bg-[var(--color-dark-hover)]',
        className,
      )}
    >
      {children}
    </tr>
  );
};

interface TableHeadProps {
  children: ReactNode;
  className?: string;
}

export const TableHead: FC<TableHeadProps> = ({ children, className = '' }) => {
  return (
    <th
      className={cn(
        'px-4 py-2 text-left text-xs font-semibold uppercase tracking-wider text-[var(--color-text-secondary)] border-b border-[var(--color-dark-border)]',
        className,
      )}
    >
      {children}
    </th>
  );
};

interface TableCellProps {
  children: ReactNode;
  className?: string;
}

export const TableCell: FC<TableCellProps> = ({ children, className = '' }) => {
  return (
    <td
      className={cn(
        'px-4 py-3 text-sm border-b border-[var(--color-dark-border)]',
        className,
      )}
    >
      {children}
    </td>
  );
};
