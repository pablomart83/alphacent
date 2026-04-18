import { type FC } from 'react';
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

  // Cap at 15 symbols to keep the heatmap readable in its container
  const displaySymbols = symbols.slice(0, 15);

  if (displaySymbols.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-muted-foreground">
        No correlation data available
      </div>
    );
  }

  // Cell size scales down with more symbols
  const cellSize = displaySymbols.length > 10 ? 24 : displaySymbols.length > 7 ? 28 : 32;
  const labelWidth = 36;

  return (
    <div className="overflow-auto max-h-[280px]">
      <table className="border-collapse text-xs font-mono" style={{ fontFamily: chartTheme.fontFamily }}>
        <thead>
          <tr>
            <th style={{ width: labelWidth, minWidth: labelWidth }} />
            {displaySymbols.map((sym) => (
              <th
                key={sym}
                style={{ width: cellSize, minWidth: cellSize, writingMode: 'vertical-rl', transform: 'rotate(180deg)', maxHeight: 50, padding: '2px 1px' }}
                className="text-center text-muted-foreground"
              >
                {sym.slice(0, 4)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displaySymbols.map((rowSym) => (
            <tr key={rowSym}>
              <td style={{ width: labelWidth, minWidth: labelWidth, padding: '1px 2px' }} className="text-right text-muted-foreground truncate">{rowSym.slice(0, 4)}</td>
              {displaySymbols.map((colSym) => {
                const val = rowSym === colSym ? 1 : (lookup.get(`${rowSym}:${colSym}`) ?? 0);
                return (
                  <td
                    key={colSym}
                    style={{ width: cellSize, height: cellSize, backgroundColor: getCorrelationBg(val), padding: 0 }}
                    className="text-center border border-dark-border/20 cursor-default"
                    title={`${rowSym} × ${colSym}: ${val.toFixed(2)}`}
                  >
                    <span style={{ fontSize: 9 }} className="text-white/80">{val.toFixed(1)}</span>
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
