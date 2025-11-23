/**
 * FAANG-Level Skeleton Loader
 * Professional loading placeholders
 */

const Skeleton = ({ 
  variant = 'default',
  width = 'full',
  height = 'default',
  rounded = 'md',
  className = '',
  animate = true,
}) => {
  const baseStyles = `
    bg-gradient-to-r from-neutral-200 via-neutral-100 to-neutral-200
    ${animate ? 'animate-pulse' : ''}
  `;
  
  const widthStyles = {
    full: 'w-full',
    '3/4': 'w-3/4',
    '1/2': 'w-1/2',
    '1/3': 'w-1/3',
    '1/4': 'w-1/4',
  };
  
  const heightStyles = {
    default: 'h-4',
    sm: 'h-3',
    md: 'h-5',
    lg: 'h-6',
    xl: 'h-8',
    '2xl': 'h-10',
    '3xl': 'h-12',
  };
  
  const roundedStyles = {
    none: 'rounded-none',
    sm: 'rounded',
    md: 'rounded-md',
    lg: 'rounded-lg',
    xl: 'rounded-xl',
    '2xl': 'rounded-2xl',
    full: 'rounded-full',
  };
  
  if (variant === 'circle') {
    return (
      <div 
        className={`
          ${baseStyles}
          aspect-square rounded-full
          ${typeof width === 'string' ? widthStyles[width] : ''}
          ${className}
        `}
        style={typeof width === 'number' ? { width, height: width } : {}}
      />
    );
  }
  
  if (variant === 'avatar') {
    return (
      <div className={`${baseStyles} w-10 h-10 rounded-full ${className}`} />
    );
  }
  
  if (variant === 'text') {
    return (
      <div 
        className={`
          ${baseStyles}
          ${widthStyles[width]}
          h-4 rounded
          ${className}
        `}
      />
    );
  }
  
  if (variant === 'button') {
    return (
      <div className={`${baseStyles} h-10 w-32 rounded-xl ${className}`} />
    );
  }
  
  // Default rectangle
  return (
    <div 
      className={`
        ${baseStyles}
        ${widthStyles[width] || width}
        ${heightStyles[height] || height}
        ${roundedStyles[rounded]}
        ${className}
      `}
    />
  );
};

// Pre-built skeleton patterns
export const SkeletonCard = ({ className = '' }) => (
  <div className={`bg-white rounded-2xl border border-neutral-200 p-6 space-y-4 ${className}`}>
    <div className="flex items-start gap-4">
      <Skeleton variant="avatar" />
      <div className="flex-1 space-y-2">
        <Skeleton width="3/4" />
        <Skeleton width="1/2" height="sm" />
      </div>
    </div>
    <Skeleton height="xl" />
    <div className="flex gap-2">
      <Skeleton variant="button" />
      <Skeleton variant="button" />
    </div>
  </div>
);

export const SkeletonText = ({ lines = 3, className = '' }) => (
  <div className={`space-y-2 ${className}`}>
    {[...Array(lines)].map((_, i) => (
      <Skeleton 
        key={i} 
        width={i === lines - 1 ? '3/4' : 'full'} 
        variant="text"
      />
    ))}
  </div>
);

export const SkeletonList = ({ items = 3, className = '' }) => (
  <div className={`space-y-3 ${className}`}>
    {[...Array(items)].map((_, i) => (
      <div key={i} className="flex items-center gap-3">
        <Skeleton variant="avatar" />
        <div className="flex-1 space-y-2">
          <Skeleton width="3/4" />
          <Skeleton width="1/2" height="sm" />
        </div>
      </div>
    ))}
  </div>
);

export default Skeleton;

