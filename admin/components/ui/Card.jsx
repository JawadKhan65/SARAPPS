/**
 * Admin Card Component
 * Professional card container with hover effects
 */
'use client';

export const Card = ({
  children,
  className = '',
  variant = 'default',
  hoverEffect = false,
  padding = 'default',
}) => {
  const variants = {
    default: 'bg-white border border-slate-200',
    elevated: 'bg-white shadow-lg border border-slate-100',
    ghost: 'bg-slate-50 border border-slate-100',
  };
  
  const paddings = {
    none: '',
    sm: 'p-4',
    default: 'p-6',
    lg: 'p-8',
  };
  
  const hoverClass = hoverEffect ? 'hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200' : '';
  
  return (
    <div className={`${variants[variant]} ${paddings[padding]} ${hoverClass} rounded-xl ${className}`}>
      {children}
    </div>
  );
};

export default Card;

