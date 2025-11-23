/**
 * FAANG-Level Button Component
 * All interactive states: hover, active, focus, disabled, loading
 * Follows Stripe/Linear patterns
 */
import { forwardRef } from 'react';

const Button = forwardRef(({ 
  children, 
  variant = 'primary', 
  size = 'md', 
  isLoading = false,
  disabled = false,
  icon,
  iconPosition = 'left',
  fullWidth = false,
  className = '',
  ...props 
}, ref) => {
  
  const baseStyles = `
    inline-flex items-center justify-center gap-2 font-semibold
    rounded-xl transition-all duration-200
    focus:outline-none focus:ring-2 focus:ring-offset-2
    disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none
    active:scale-[0.98]
  `;
  
  const variants = {
    primary: `
      bg-gradient-to-r from-blue-600 to-purple-600 text-white
      hover:from-blue-700 hover:to-purple-700 hover:shadow-lg
      focus:ring-purple-500
      shadow-md
    `,
    secondary: `
      bg-neutral-100 text-neutral-900
      hover:bg-neutral-200 hover:shadow-md
      focus:ring-neutral-500
      border border-neutral-200
    `,
    outline: `
      bg-transparent text-neutral-700 border-2 border-neutral-300
      hover:bg-neutral-50 hover:border-neutral-400 hover:shadow-sm
      focus:ring-neutral-500
    `,
    ghost: `
      bg-transparent text-neutral-700
      hover:bg-neutral-100 hover:shadow-sm
      focus:ring-neutral-500
    `,
    danger: `
      bg-gradient-to-r from-red-500 to-red-600 text-white
      hover:from-red-600 hover:to-red-700 hover:shadow-lg
      focus:ring-red-500
      shadow-md
    `,
    success: `
      bg-gradient-to-r from-green-500 to-green-600 text-white
      hover:from-green-600 hover:to-green-700 hover:shadow-lg
      focus:ring-green-500
      shadow-md
    `,
  };
  
  const sizes = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-5 py-2.5 text-base',
    lg: 'px-6 py-3 text-lg',
    xl: 'px-8 py-4 text-xl',
  };
  
  const isDisabled = disabled || isLoading;
  
  return (
    <button
      ref={ref}
      disabled={isDisabled}
      className={`
        ${baseStyles}
        ${variants[variant]}
        ${sizes[size]}
        ${fullWidth ? 'w-full' : ''}
        ${className}
      `}
      {...props}
    >
      {/* Loading Spinner */}
      {isLoading && (
        <svg 
          className="animate-spin h-5 w-5" 
          fill="none" 
          viewBox="0 0 24 24"
          aria-label="Loading"
        >
          <circle 
            className="opacity-25" 
            cx="12" 
            cy="12" 
            r="10" 
            stroke="currentColor" 
            strokeWidth="4"
          />
          <path 
            className="opacity-75" 
            fill="currentColor" 
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      )}
      
      {/* Left Icon */}
      {icon && iconPosition === 'left' && !isLoading && (
        <span className="flex-shrink-0">{icon}</span>
      )}
      
      {/* Button Text */}
      <span>{children}</span>
      
      {/* Right Icon */}
      {icon && iconPosition === 'right' && !isLoading && (
        <span className="flex-shrink-0">{icon}</span>
      )}
    </button>
  );
});

Button.displayName = 'Button';

export default Button;

