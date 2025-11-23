/**
 * FAANG-Level Card Component
 * Flexible card with hover states and variants
 * Inspired by Vercel and Linear
 */
import { forwardRef } from 'react';

const Card = forwardRef(({ 
  children, 
  variant = 'default',
  hoverable = false,
  clickable = false,
  padding = 'md',
  className = '',
  ...props 
}, ref) => {
  
  const baseStyles = `
    bg-white rounded-2xl border transition-all duration-200
  `;
  
  const variants = {
    default: `
      border-neutral-200
      ${hoverable || clickable ? 'hover:border-neutral-300 hover:shadow-lg' : 'shadow-sm'}
    `,
    elevated: `
      border-neutral-200 shadow-md
      ${hoverable || clickable ? 'hover:shadow-xl hover:border-neutral-300' : ''}
    `,
    outlined: `
      border-2 border-neutral-300
      ${hoverable || clickable ? 'hover:border-neutral-400 hover:shadow-md' : ''}
    `,
    gradient: `
      border-0 bg-gradient-to-br from-blue-50 via-purple-50 to-pink-50 shadow-md
      ${hoverable || clickable ? 'hover:shadow-xl' : ''}
    `,
  };
  
  const paddings = {
    none: 'p-0',
    sm: 'p-4',
    md: 'p-6',
    lg: 'p-8',
    xl: 'p-10',
  };
  
  const interactiveStyles = clickable ? 'cursor-pointer active:scale-[0.99]' : '';
  const hoverStyles = hoverable || clickable ? 'hover:-translate-y-1' : '';
  
  return (
    <div
      ref={ref}
      className={`
        ${baseStyles}
        ${variants[variant]}
        ${paddings[padding]}
        ${interactiveStyles}
        ${hoverStyles}
        ${className}
      `}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      {...props}
    >
      {children}
    </div>
  );
});

Card.displayName = 'Card';

// Card Sub-components
export const CardHeader = ({ children, className = '' }) => (
  <div className={`mb-4 ${className}`}>
    {children}
  </div>
);

export const CardTitle = ({ children, className = '' }) => (
  <h3 className={`text-xl font-bold text-neutral-900 ${className}`}>
    {children}
  </h3>
);

export const CardDescription = ({ children, className = '' }) => (
  <p className={`text-sm text-neutral-600 mt-1 ${className}`}>
    {children}
  </p>
);

export const CardContent = ({ children, className = '' }) => (
  <div className={className}>
    {children}
  </div>
);

export const CardFooter = ({ children, className = '' }) => (
  <div className={`mt-6 pt-4 border-t border-neutral-200 ${className}`}>
    {children}
  </div>
);

export default Card;

