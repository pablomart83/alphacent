import { useEffect } from 'react';
import { motion, useSpring, useTransform } from 'framer-motion';

interface AnimatedNumberProps {
  value: number;
  format?: 'number' | 'currency' | 'percentage';
  decimals?: number;
  className?: string;
}

export function AnimatedNumber({ 
  value, 
  format = 'number', 
  decimals = 2,
  className = '' 
}: AnimatedNumberProps) {
  const spring = useSpring(value, { 
    stiffness: 100, 
    damping: 30,
    mass: 0.8
  });
  
  const display = useTransform(spring, (current) => {
    const num = Number(current);
    
    switch (format) {
      case 'currency':
        return new Intl.NumberFormat('en-US', {
          style: 'currency',
          currency: 'USD',
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        }).format(num);
      
      case 'percentage':
        return new Intl.NumberFormat('en-US', {
          style: 'percent',
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
          signDisplay: 'exceptZero',
        }).format(num / 100);
      
      default:
        return new Intl.NumberFormat('en-US', {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        }).format(num);
    }
  });

  // Update spring value when prop changes
  useEffect(() => {
    spring.set(value);
  }, [value, spring]);

  return <motion.span className={className}>{display}</motion.span>;
}

// Simpler version for integers
export function AnimatedInteger({ 
  value, 
  className = '' 
}: { value: number; className?: string }) {
  const spring = useSpring(value, { 
    stiffness: 100, 
    damping: 30 
  });
  
  const display = useTransform(spring, (current) =>
    Math.round(current).toLocaleString()
  );

  useEffect(() => {
    spring.set(value);
  }, [value, spring]);

  return <motion.span className={className}>{display}</motion.span>;
}
