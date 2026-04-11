import { type FC } from 'react';
import { cn } from '../../lib/utils';
import { chartTheme } from '../../lib/design-tokens';

export interface CorrelationHeatmapProps {
  /** Array of { symbol1, symbol2, correlation } or a matrix format */
  data: Array<Record<string, number | string>>;
  /** Symbols to display */
  symbols: string[];
}

/** Color for a correlation value: red for high positive, blue for negative, green for low */
function getCorrelationColor(value: number): string {
  if (value >= 0.7) return '#ef4444';
  if (value >= 0.4) return '#f59e0b';
  if (value >= 0.1) return '#22c55e';
  if (value >= -0.3) return '#3b82f6';
  return '#6366f1';
}

function getCorrelationBg(value: number): string {
  const alpha = Math.min(Math.abs(value) * 0.6 + 0.1, 0.7);
  const color = getCorrelationColor(value);
  return `${color}${Math.round(alpha * 255).toString(16).padStart(2, '0')}`;
}

export const CorrelationHeatmap: FC<CorrelationHeatmapProps> = ({ data, symbols }) => {
  // Build a lookup map from the flat data array
  const lookup = new Map<string, number>();
  data.forEach((row) => {
    const s1 = String(row.symbol1 || row.row || '');
    const s2 = String(row.symbol2 || row.col || '');
    const corr = Number(row.correlation ?? row.value ?? 0);
    if (s1 && s2) {
      lookup.set(`${s1}:${s2}`, corr);
      lookup.set(`${s2}:${s1}`, corr);
    }
  });

  const displaySymbols = symbols.slice(0, 20);

  if (displaySymbols.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-muted-foreground">
        No correlation data available
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-xs font-mono" style={{ fontFamily: chartTheme.fontFamily }}>
        <thead>
          <tr>
            <th className="p-1 text-right text-muted-foreground w-16" />
            {displaySymbols.map((sym) => (
              <th
                key={sym}
                className="p-1 text-center text-muted-foreground w-12"
                style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', maxHeight: 60 }}
              >
                {sym.slice(0, 5)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displaySymbols.map((rowSym) => (
            <tr key={rowSym}>
              <td className="p-1 text-right text-muted-foreground truncate max-w-[60px]">{rowSym.slice(0, 5)}</td>
              {displaySymbols.map((colSym) => {
                const val = rowSym === colSym ? 1 : (lookup.get(`${rowSym}:${colSym}`) ?? 0);
                return (
                  <td
                    key={colSym}
                    className={cn('p-1 text-center w-12 h-8 border border-dark-border/30 cursor-default')}
                    style={{ backgroundColor: getCorrelationBg(val) }}
                    title={`${rowSym} × ${colSym}: ${val.toFixed(2)}`}
                  >
                    <span className="text-[9px] text-white/80">{val.toFixed(1)}</span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {/* Legend */}
      <div className="flex items-center gap-3 mt-3 text-xs text-muted-foreground">
        <span>Legend:</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ backgroundColor: '#6366f1' }} /> &lt;-0.3</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ backgroundColor: '#3b82f6' }} /> -0.3–0.1</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ backgroundColor: '#22c55e' }} /> 0.1–0.4</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ backgroundColor: '#f59e0b' }} /> 0.4–0.7</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ backgroundColor: '#ef4444' }} /> &gt;0.7</span>
      </div>
    </div>
  );
};
