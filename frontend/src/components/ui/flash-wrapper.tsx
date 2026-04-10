import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { cn } from '../../lib/utils';

interface FlashWrapperProps {
  value: any;
  children: React.ReactNode;
  className?: string;
  flashColor?: 'green' | 'red' | 'blue' | 'yellow';
  duration?: number;
}

export function FlashWrapper({ 
  value, 
  children, 
  className = '',
  flashColor = 'blue',
  duration = 500
}: FlashWrapperProps) {
  const [isFlashing, setIsFlashing] = useState(false);
  const prevValueRef = useState(value)[0];

  useEffect(() => {
    if (value !== prevValueRef) {
      setIsFlashing(true);
      const timer = setTimeout(() => setIsFlashing(false), duration);
      return () => clearTimeout(timer);
    }
  }, [value, prevValueRef, duration]);

  const flashColors = {
    green: 'bg-accent-green/20',
    red: 'bg-accent-red/20',
    blue: 'bg-blue-500/20',
    yellow: 'bg-yellow-500/20',
  };

  return (
    <motion.div
      className={cn('relative', className)}
      animate={{
        backgroundColor: isFlashing ? flashColors[flashColor] : 'transparent',
      }}
      transition={{ duration: duration / 1000 }}
    >
      {children}
    </motion.div>
  );
}
