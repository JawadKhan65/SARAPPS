/**
 * FAANG-Level Badge Component
 * Status indicators and labels with semantic colors
 */
import { forwardRef } from 'react';

const Badge = forwardRef(({ 
  children, 
  variant = 'default',
  size = 'md',
  rounded = 'full',
  className = '',
  ...props 
}, ref) => {
  
  const baseStyles = `
    inline-flex items-center justify-center gap-1.5 font-semibold
    transition-all duration-200
  `;
  
  const variants = {
    default: 'bg-neutral-100 text-neutral-700 border border-neutral-200',
    primary: 'bg-blue-100 text-blue-700 border border-blue-200',
    secondary: 'bg-purple-100 text-purple-700 border border-purple-200',
    success: 'bg-green-100 text-green-700 border border-green-200',
    warning: 'bg-yellow-100 text-yellow-700 border border-yellow-200',
    error: 'bg-red-100 text-red-700 border border-red-200',
    info: 'bg-cyan-100 text-cyan-700 border border-cyan-200',
    
    // Solid variants
    solidPrimary: 'bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-md',
    solidSecondary: 'bg-gradient-to-r from-purple-500 to-purple-600 text-white shadow-md',
    solidSuccess: 'bg-gradient-to-r from-green-500 to-green-600 text-white shadow-md',
    solidWarning: 'bg-gradient-to-r from-yellow-500 to-yellow-600 text-white shadow-md',
    solidError: 'bg-gradient-to-r from-red-500 to-red-600 text-white shadow-md',
  };
  
  const sizes = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-1 text-sm',
    lg: 'px-3 py-1.5 text-base',
  };
  
  const roundedStyles = {
    none: 'rounded-none',
    sm: 'rounded',
    md: 'rounded-lg',
    lg: 'rounded-xl',
    full: 'rounded-full',
  };
  
  return (
    <span
      ref={ref}
      className={`
        ${baseStyles}
        ${variants[variant]}
        ${sizes[size]}
        ${roundedStyles[rounded]}
        ${className}
      `}
      {...props}
    >
      {children}
    </span>
  );
});

Badge.displayName = 'Badge';

export default Badge;

