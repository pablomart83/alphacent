import { type FC, useState, useCallback, useRef } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { Button } from '../ui/Button';
import { cn } from '../../lib/utils';
import { useTradingMode } from '../../contexts/TradingModeContext';
import { apiClient } from '../../services/api';
import { toast } from 'sonner';

// ── Types ──────────────────────────────────────────────────────────────────

type TearSheetPeriod = '1M' | '3M' | '6M' | '1Y' | 'ALL';

interface TearSheetGeneratorProps {
  /** Optional class name for the wrapper */
  className?: string;
}

const PERIOD_OPTIONS: Array<{ value: TearSheetPeriod; label: string }> = [
  { value: '1M', label: '1 Month' },
  { value: '3M', label: '3 Months' },
  { value: '6M', label: '6 Months' },
  { value: '1Y', label: '1 Year' },
  { value: 'ALL', label: 'All Time' },
];

// ── Helpers ────────────────────────────────────────────────────────────────

function formatDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function buildFilename(period: TearSheetPeriod): string {
  return `AlphaCent_TearSheet_${period}_${formatDate(new Date())}.pdf`;
}

// ── PDF Generation ─────────────────────────────────────────────────────────

async function generatePDF(
  tradingMode: string,
  period: TearSheetPeriod,
  onProgress: (msg: string) => void,
): Promise<Blob> {
  // Dynamic imports to avoid loading heavy libs until needed
  const [{ default: jsPDF }, { default: html2canvas }] = await Promise.all([
    import('jspdf'),
    import('html2canvas'),
  ]);

  onProgress('Fetching data…');

  // Fetch all data in parallel
  const [dashData, tearSheetData, , perfData] = await Promise.all([
    apiClient.getDashboardSummary(tradingMode as any).catch(() => null),
    apiClient.getTearSheetData(tradingMode as any, period).catch(() => null),
    apiClient.getSpyBenchmark(period).catch(() => null),
    apiClient.getPerformanceAnalytics(tradingMode as any, period).catch(() => null),
  ]);

  onProgress('Composing PDF…');

  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
  const pageWidth = pdf.internal.pageSize.getWidth();
  const margin = 15;
  const contentWidth = pageWidth - margin * 2;
  let y = margin;

  // ── Header ─────────────────────────────────────────────────────────────
  pdf.setFillColor(17, 24, 39); // #111827
  pdf.rect(0, 0, pageWidth, 35, 'F');

  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(18);
  pdf.setTextColor(34, 197, 94); // #22c55e
  pdf.text('AlphaCent', margin, 15);

  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(10);
  pdf.setTextColor(156, 163, 175); // #9ca3af
  pdf.text('Performance Tear Sheet', margin, 22);

  pdf.setFontSize(9);
  pdf.text(`Period: ${period}  |  Generated: ${formatDate(new Date())}`, margin, 29);

  y = 42;

  // ── Key Stats Table ────────────────────────────────────────────────────
  onProgress('Writing key statistics…');

  pdf.setTextColor(243, 244, 246); // #f3f4f6
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(12);
  pdf.text('Key Statistics', margin, y);
  y += 7;

  const stats: Array<[string, string]> = [];

  if (perfData) {
    stats.push(['Total Return', `${(perfData.total_return ?? 0).toFixed(2)}%`]);
    stats.push(['Sharpe Ratio', `${(perfData.sharpe_ratio ?? 0).toFixed(2)}`]);
    stats.push(['Max Drawdown', `${(perfData.max_drawdown ?? 0).toFixed(2)}%`]);
    stats.push(['Win Rate', `${(perfData.win_rate ?? 0).toFixed(1)}%`]);
    stats.push(['Profit Factor', `${(perfData.profit_factor ?? 0).toFixed(2)}`]);
    stats.push(['Total Trades', `${perfData.total_trades ?? 0}`]);
  }

  if (dashData) {
    stats.push(['Account Equity', `$${(dashData.account_equity ?? 0).toLocaleString()}`]);
  }

  if (stats.length > 0) {
    const colWidth = contentWidth / 2;
    const rowHeight = 6;

    // Table header
    pdf.setFillColor(31, 41, 55); // #1f2937
    pdf.rect(margin, y, contentWidth, rowHeight, 'F');
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(8);
    pdf.setTextColor(156, 163, 175);
    pdf.text('Metric', margin + 2, y + 4);
    pdf.text('Value', margin + colWidth + 2, y + 4);
    y += rowHeight;

    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(8);
    for (let i = 0; i < stats.length; i++) {
      if (i % 2 === 0) {
        pdf.setFillColor(17, 24, 39);
        pdf.rect(margin, y, contentWidth, rowHeight, 'F');
      }
      pdf.setTextColor(229, 231, 235);
      pdf.text(stats[i][0], margin + 2, y + 4);
      pdf.text(stats[i][1], margin + colWidth + 2, y + 4);
      y += rowHeight;
    }
    y += 5;
  }

  // ── Capture charts from DOM ────────────────────────────────────────────
  onProgress('Capturing charts…');

  const chartSections: Array<{ selector: string; label: string }> = [
    { selector: '[data-pdf-chart="equity-curve"]', label: 'Equity Curve' },
    { selector: '[data-pdf-chart="monthly-returns"]', label: 'Monthly Returns Heatmap' },
    { selector: '[data-pdf-chart="drawdown"]', label: 'Drawdown Chart' },
  ];

  const failedSections: string[] = [];

  for (const section of chartSections) {
    const el = document.querySelector(section.selector) as HTMLElement | null;
    if (!el) {
      failedSections.push(section.label);
      continue;
    }

    try {
      onProgress(`Capturing ${section.label}…`);
      const canvas = await html2canvas(el, {
        backgroundColor: '#111827',
        scale: 2,
        logging: false,
        useCORS: true,
      });

      const imgData = canvas.toDataURL('image/png');
      const imgWidth = contentWidth;
      const imgHeight = (canvas.height / canvas.width) * imgWidth;

      // Check if we need a new page
      if (y + imgHeight + 12 > pdf.internal.pageSize.getHeight() - margin) {
        pdf.addPage();
        y = margin;
      }

      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(10);
      pdf.setTextColor(243, 244, 246);
      pdf.text(section.label, margin, y);
      y += 5;

      pdf.addImage(imgData, 'PNG', margin, y, imgWidth, imgHeight);
      y += imgHeight + 8;
    } catch {
      failedSections.push(section.label);
    }
  }

  // ── Sector Exposure ────────────────────────────────────────────────────
  if (dashData?.sector_exposure && Array.isArray(dashData.sector_exposure) && dashData.sector_exposure.length > 0) {
    onProgress('Writing sector exposure…');

    if (y + 60 > pdf.internal.pageSize.getHeight() - margin) {
      pdf.addPage();
      y = margin;
    }

    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(10);
    pdf.setTextColor(243, 244, 246);
    pdf.text('Sector Exposure', margin, y);
    y += 6;

    const colW = contentWidth / 3;
    const rh = 5.5;

    pdf.setFillColor(31, 41, 55);
    pdf.rect(margin, y, contentWidth, rh, 'F');
    pdf.setFontSize(7);
    pdf.setTextColor(156, 163, 175);
    pdf.text('Sector', margin + 2, y + 3.5);
    pdf.text('Allocation %', margin + colW + 2, y + 3.5);
    pdf.text('P&L', margin + colW * 2 + 2, y + 3.5);
    y += rh;

    pdf.setFont('helvetica', 'normal');
    const sectors = dashData.sector_exposure.slice(0, 10);
    for (let i = 0; i < sectors.length; i++) {
      const s = sectors[i];
      if (i % 2 === 0) {
        pdf.setFillColor(17, 24, 39);
        pdf.rect(margin, y, contentWidth, rh, 'F');
      }
      pdf.setTextColor(229, 231, 235);
      pdf.text(String(s.sector || ''), margin + 2, y + 3.5);
      pdf.text(`${(s.allocation_pct ?? 0).toFixed(1)}%`, margin + colW + 2, y + 3.5);
      const pnl = s.pnl ?? 0;
      pdf.setTextColor(pnl >= 0 ? 34 : 239, pnl >= 0 ? 197 : 68, pnl >= 0 ? 94 : 68);
      pdf.text(`$${pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, margin + colW * 2 + 2, y + 3.5);
      y += rh;
    }
    y += 5;
  }

  // ── Top / Bottom Performers ────────────────────────────────────────────
  if (tearSheetData?.annual_returns || perfData) {
    onProgress('Writing performers…');

    // Try to get top/bottom from sector exposure P&L as a proxy
    if (dashData?.sector_exposure && dashData.sector_exposure.length > 0) {
      const sorted = [...dashData.sector_exposure].sort((a: any, b: any) => (b.pnl ?? 0) - (a.pnl ?? 0));
      const top5 = sorted.slice(0, 5);
      const bottom5 = sorted.slice(-5).reverse();

      if (y + 50 > pdf.internal.pageSize.getHeight() - margin) {
        pdf.addPage();
        y = margin;
      }

      for (const [label, list] of [['Top 5 Performers', top5], ['Bottom 5 Performers', bottom5]] as const) {
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(10);
        pdf.setTextColor(243, 244, 246);
        pdf.text(label, margin, y);
        y += 5;

        pdf.setFont('helvetica', 'normal');
        pdf.setFontSize(8);
        for (const item of list) {
          const pnl = (item as any).pnl ?? 0;
          pdf.setTextColor(pnl >= 0 ? 34 : 239, pnl >= 0 ? 197 : 68, pnl >= 0 ? 94 : 68);
          pdf.text(
            `${(item as any).sector}: $${pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
            margin + 2,
            y + 3,
          );
          y += 5;
        }
        y += 3;
      }
    }
  }

  // ── Footer ─────────────────────────────────────────────────────────────
  const pageCount = pdf.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    pdf.setPage(i);
    pdf.setFontSize(7);
    pdf.setTextColor(107, 114, 128);
    pdf.text(
      `AlphaCent Tear Sheet — Page ${i} of ${pageCount}`,
      pageWidth / 2,
      pdf.internal.pageSize.getHeight() - 8,
      { align: 'center' },
    );
  }

  if (failedSections.length > 0) {
    toast.warning(`Some sections unavailable: ${failedSections.join(', ')}. Partial report generated.`);
  }

  return pdf.output('blob');
}

// ── Component ──────────────────────────────────────────────────────────────

export const TearSheetGenerator: FC<TearSheetGeneratorProps> = ({ className }) => {
  const { tradingMode } = useTradingMode();
  const [generating, setGenerating] = useState(false);
  const [_progress, setProgress] = useState('');
  const [showPeriodPicker, setShowPeriodPicker] = useState(false);
  const [selectedPeriod, setSelectedPeriod] = useState<TearSheetPeriod>('3M');
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Close period picker on outside click
  const handleBlur = useCallback((e: React.FocusEvent) => {
    if (wrapperRef.current && !wrapperRef.current.contains(e.relatedTarget as Node)) {
      setShowPeriodPicker(false);
    }
  }, []);

  return (
    <div ref={wrapperRef} className={cn('relative inline-flex items-center gap-1', className)} onBlur={handleBlur}>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setShowPeriodPicker((p) => !p)}
        disabled={generating}
        className="gap-1 h-7 w-7 p-0"
        title="Download Tear Sheet"
      >
        {generating ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Download className="h-3.5 w-3.5" />
        )}
      </Button>

      {showPeriodPicker && !generating && (
        <div className="absolute top-full right-0 mt-1 z-50 bg-dark-surface border border-dark-border rounded-lg shadow-xl py-1 min-w-[160px]">
          <div className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Select Period
          </div>
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => {
                setSelectedPeriod(opt.value);
                // Auto-generate after selecting period
                setShowPeriodPicker(false);
                setTimeout(() => {
                  // Trigger generation
                  setGenerating(true);
                  generatePDF(tradingMode!, opt.value, setProgress)
                    .then((blob) => {
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = buildFilename(opt.value);
                      document.body.appendChild(a);
                      a.click();
                      URL.revokeObjectURL(url);
                      document.body.removeChild(a);
                      toast.success('Tear sheet downloaded');
                    })
                    .catch(() => {
                      toast.error('Failed to generate tear sheet');
                    })
                    .finally(() => {
                      setGenerating(false);
                      setProgress('');
                    });
                }, 50);
              }}
              className={cn(
                'w-full text-left px-3 py-2 text-sm hover:bg-dark-bg transition-colors flex items-center justify-between',
                selectedPeriod === opt.value ? 'text-accent-green' : 'text-gray-300',
              )}
            >
              <span>{opt.label}</span>
              {selectedPeriod === opt.value && <span className="text-accent-green text-xs">✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

/** Helper to generate the tear sheet filename — exported for testing */
export { buildFilename };
