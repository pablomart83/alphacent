import { type FC, type ReactNode } from 'react';

interface TableProps {
  children: ReactNode;
  className?: string;
}

export const Table: FC<TableProps> = ({ children, className = '' }) => {
  return (
    <div className="overflow-x-auto">
      <table className={`table ${className}`}>{children}</table>
    </div>
  );
};

interface TableHeaderProps {
  children: ReactNode;
}

export const TableHeader: FC<TableHeaderProps> = ({ children }) => {
  return <thead>{children}</thead>;
};

interface TableBodyProps {
  children: ReactNode;
}

export const TableBody: FC<TableBodyProps> = ({ children }) => {
  return <tbody>{children}</tbody>;
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
      className={`${onClick ? 'cursor-pointer' : ''} ${className}`}
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
  return <th className={className}>{children}</th>;
};

interface TableCellProps {
  children: ReactNode;
  className?: string;
}

export const TableCell: FC<TableCellProps> = ({ children, className = '' }) => {
  return <td className={className}>{children}</td>;
};
