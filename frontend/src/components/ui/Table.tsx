import { type FC, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface TableProps {
  children: ReactNode;
  className?: string;
  /** Use dense variant with 32px rows, 12px font, tighter padding */
  dense?: boolean;
}

export const Table: FC<TableProps> = ({ children, className = '', dense = false }) => {
  return (
    <div className="overflow-x-auto">
      <table className={cn('table w-full', dense && 'table-dense', className)}>{children}</table>
    </div>
  );
};

/** DenseTable — convenience wrapper with dense=true by default */
export const DenseTable: FC<Omit<TableProps, 'dense'>> = ({ children, className = '' }) => {
  return <Table dense className={className}>{children}</Table>;
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
        'transition-colors duration-150 even:bg-[var(--color-table-alt-row)] hover:bg-[var(--color-dark-hover)]',
        onClick && 'cursor-pointer',
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
        // Dense variant: tighter padding
        '[.table-dense_&]:px-2 [.table-dense_&]:py-1 [.table-dense_&]:text-[12px]',
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
        'px-4 py-3 text-[13px] border-b border-[var(--color-dark-border)]',
        // Dense variant: 32px rows, 13px font, 8px/4px padding
        '[.table-dense_&]:px-2 [.table-dense_&]:py-1 [.table-dense_&]:text-[13px] [.table-dense_&]:leading-[32px]',
        className,
      )}
    >
      {children}
    </td>
  );
};
