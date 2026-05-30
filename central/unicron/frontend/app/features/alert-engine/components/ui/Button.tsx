import React from "react";

interface ButtonProps {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: 'primary' | 'secondary' | 'danger' | 'success' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  disabled?: boolean;
  type?: 'button' | 'submit';
  loading?: boolean;
  title?: string;
}

const Button: React.FC<ButtonProps> = ({
  children,
  onClick,
  variant = 'primary',
  size = 'md',
  className = '',
  disabled = false,
  type = 'button',
  loading = false,
  title
}) => {
  const baseClasses = 'btn';
  const variants = {
    primary: 'btn-primary',
    secondary: 'btn-secondary',
    danger: 'btn-danger',
    success: 'bg-success text-success-950 hover:brightness-110 active:brightness-90 focus-visible:ring-success shadow-lg hover:shadow-xl transform hover:-translate-y-0.5',
    outline: 'border border-divider text-text bg-transparent hover:bg-foreground/5 hover:border-neutral/40 focus-visible:ring-primary shadow-sm hover:shadow-md'
  };
  const sizes = {
    sm: 'px-3 py-2 text-sm h-9',
    md: 'px-4 py-2.5 text-sm h-11',
    lg: 'px-6 py-3 text-base h-12'
  };

  const isDisabled = disabled || loading;

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={isDisabled}
      title={title}
      className={`${baseClasses} ${variants[variant]} ${sizes[size]} ${isDisabled ? 'opacity-50 cursor-not-allowed transform-none' : ''} ${className}`}
    >
      {loading && (
        <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin mr-2 inline-block"></div>
      )}
      {children}
    </button>
  );
};

export default Button;
