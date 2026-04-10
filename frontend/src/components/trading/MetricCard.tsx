import { motion } from 'framer-motion';
import { memo } from 'react';
import { TrendingUp, TrendingDown, LucideIcon } from 'lucide-react';
import { cn, getValueColor } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { AnimatedNumber, AnimatedInteger } from '@/components/ui/animated-number';
import { HoverLift } from '@/components/ui/micro-interactions';

interface MetricCardProps {
  label: string;
  value: string | number;
  change?: number;
  trend?: 'up' | 'down' | 'neutral';
  tooltip?: string;
  icon?: LucideIcon;
  format?: 'currency' | 'percentage' | 'number' | 'text';
  className?: string;
  loading?: boolean;
}

export const MetricCard = memo(function MetricCard({
  label,
  value,
  change,
  trend,
  tooltip,
  icon: Icon,
  format = 'text',
  className,
  loading = false,
}: MetricCardProps) {
  const trendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : null;
  const TrendIcon = trendIcon;

  // Render animated number for numeric values
  const renderValue = () => {
    if (loading) return <span className="animate-pulse">---</span>;
    if (typeof value === 'string') return value;
    
    switch (format) {
      case 'currency':
        return <AnimatedNumber value={value} format="currency" decimals={2} />;
      case 'percentage':
        return <AnimatedNumber value={value} format="percentage" decimals={2} />;
      case 'number':
        if (Number.isInteger(value)) {
          return <AnimatedInteger value={value} />;
        }
        return <AnimatedNumber value={value} format="number" decimals={2} />;
      default:
        return value.toString();
    }
  };

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <HoverLift lift={2}>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className={cn(
                'bg-card border border-border rounded-lg p-4 hover:border-accent transition-colors cursor-default',
                className
              )}
            >
              <div className="flex items-start justify-between mb-2">
                <p className="text-sm text-muted-foreground">{label}</p>
                {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
              </div>
              
              <div className="mb-2">
                <p className="text-2xl font-bold font-mono">
                  {renderValue()}
                </p>
              </div>

              {change !== undefined && !loading && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.1 }}
                  className={cn(
                    'flex items-center gap-1 text-sm',
                    getValueColor(change)
                  )}
                >
                  {TrendIcon && <TrendIcon size={16} />}
                  <AnimatedNumber value={change} format="percentage" decimals={2} />
                </motion.div>
              )}
            </motion.div>
          </HoverLift>
        </TooltipTrigger>
        {tooltip && (
          <TooltipContent>
            <div className="min-w-[200px] max-w-sm whitespace-normal break-words">
              {tooltip}
            </div>
          </TooltipContent>
        )}
      </Tooltip>
    </TooltipProvider>
  );
});
