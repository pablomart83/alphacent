import { Variants } from 'framer-motion';

// Page transition variants
export const pageTransition: Variants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 },
};

// Card entrance variants
export const cardEntrance: Variants = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
};

// Stagger container variants
export const staggerContainer: Variants = {
  animate: {
    transition: {
      staggerChildren: 0.05,
    },
  },
};

// Stagger item variants
export const staggerItem: Variants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
};

// Fade in variants
export const fadeIn: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
};

// Scale variants
export const scaleIn: Variants = {
  initial: { scale: 0.9, opacity: 0 },
  animate: { scale: 1, opacity: 1 },
  exit: { scale: 0.9, opacity: 0 },
};

// Slide variants
export const slideUp: Variants = {
  initial: { y: 20, opacity: 0 },
  animate: { y: 0, opacity: 1 },
  exit: { y: -20, opacity: 0 },
};

export const slideDown: Variants = {
  initial: { y: -20, opacity: 0 },
  animate: { y: 0, opacity: 1 },
  exit: { y: 20, opacity: 0 },
};

export const slideLeft: Variants = {
  initial: { x: 20, opacity: 0 },
  animate: { x: 0, opacity: 1 },
  exit: { x: -20, opacity: 0 },
};

export const slideRight: Variants = {
  initial: { x: -20, opacity: 0 },
  animate: { x: 0, opacity: 1 },
  exit: { x: 20, opacity: 0 },
};

// Transition presets
export const springTransition = {
  type: 'spring' as const,
  stiffness: 400,
  damping: 17,
};

export const smoothTransition = {
  duration: 0.3,
  ease: 'easeInOut' as const,
};

export const fastTransition = {
  duration: 0.15,
  ease: 'easeOut' as const,
};

export const slowTransition = {
  duration: 0.5,
  ease: 'easeInOut' as const,
};

// Hover animations
export const hoverScale = {
  scale: 1.02,
  transition: springTransition,
};

export const hoverLift = {
  y: -4,
  transition: springTransition,
};

export const tapScale = {
  scale: 0.95,
  transition: springTransition,
};

// Flash animation for real-time updates
export function createFlashAnimation(color: string = 'rgba(59, 130, 246, 0.2)') {
  return {
    backgroundColor: [
      'transparent',
      color,
      'transparent',
    ],
    transition: {
      duration: 0.5,
      ease: 'easeInOut',
    },
  };
}

// Pulse animation
export const pulseAnimation = {
  scale: [1, 1.05, 1],
  transition: {
    duration: 2,
    repeat: Infinity,
    ease: 'easeInOut' as const,
  },
};

// Shimmer animation
export const shimmerAnimation = {
  x: ['-100%', '100%'],
  transition: {
    duration: 1.5,
    repeat: Infinity,
    ease: 'linear' as const,
  },
};

// Number counter animation config
export const numberCounterConfig = {
  stiffness: 100,
  damping: 30,
  mass: 0.8,
};

// Chart animation config
export const chartAnimationConfig = {
  duration: 0.8,
  ease: 'easeOut' as const,
};
