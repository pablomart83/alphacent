import { motion } from 'framer-motion';
import { cn } from '../../lib/utils';

// Hover scale effect
export function HoverScale({ 
  children, 
  scale = 1.02,
  className = '' 
}: { 
  children: React.ReactNode; 
  scale?: number;
  className?: string;
}) {
  return (
    <motion.div
      whileHover={{ scale }}
      whileTap={{ scale: scale * 0.98 }}
      transition={{ type: 'spring', stiffness: 400, damping: 17 }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// Hover lift effect
export function HoverLift({ 
  children, 
  lift = 4,
  className = '' 
}: { 
  children: React.ReactNode; 
  lift?: number;
  className?: string;
}) {
  return (
    <motion.div
      whileHover={{ y: -lift }}
      transition={{ type: 'spring', stiffness: 400, damping: 17 }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// Press effect
export function PressEffect({ 
  children, 
  className = '' 
}: { 
  children: React.ReactNode; 
  className?: string;
}) {
  return (
    <motion.div
      whileTap={{ scale: 0.95 }}
      transition={{ type: 'spring', stiffness: 400, damping: 17 }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// Pulse animation
export function Pulse({ 
  children, 
  className = '' 
}: { 
  children: React.ReactNode; 
  className?: string;
}) {
  return (
    <motion.div
      animate={{
        scale: [1, 1.05, 1],
      }}
      transition={{
        duration: 2,
        repeat: Infinity,
        ease: 'easeInOut',
      }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// Shimmer effect
export function Shimmer({ 
  className = '' 
}: { 
  className?: string;
}) {
  return (
    <motion.div
      className={cn(
        'absolute inset-0 -translate-x-full',
        'bg-gradient-to-r from-transparent via-white/10 to-transparent',
        className
      )}
      animate={{
        translateX: ['100%', '100%'],
      }}
      transition={{
        duration: 1.5,
        repeat: Infinity,
        ease: 'linear',
      }}
    />
  );
}

// Fade in on scroll
export function FadeInOnScroll({ 
  children, 
  className = '' 
}: { 
  children: React.ReactNode; 
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-50px' }}
      transition={{ duration: 0.5 }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// Rotate on hover
export function RotateOnHover({ 
  children, 
  degrees = 180,
  className = '' 
}: { 
  children: React.ReactNode; 
  degrees?: number;
  className?: string;
}) {
  return (
    <motion.div
      whileHover={{ rotate: degrees }}
      transition={{ type: 'spring', stiffness: 200, damping: 10 }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// Bounce on mount
export function BounceOnMount({ 
  children, 
  className = '' 
}: { 
  children: React.ReactNode; 
  className?: string;
}) {
  return (
    <motion.div
      initial={{ scale: 0 }}
      animate={{ scale: 1 }}
      transition={{
        type: 'spring',
        stiffness: 260,
        damping: 20,
      }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
