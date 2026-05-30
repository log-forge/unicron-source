import React, { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, X, Check } from "lucide-react";

interface Option {
  value: string;
  label: string;
  subtitle?: string;
}

interface MultiSelectProps {
  options: Option[];
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  className?: string;
}

const MultiSelect: React.FC<MultiSelectProps> = ({
  options,
  value,
  onChange,
  placeholder = "Select options...",
  className = ""
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const triggerRef = useRef<HTMLDivElement>(null);
  const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties | null>(null);

  const updateDropdownPosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger || typeof window === 'undefined') {
      return;
    }

    const rect = trigger.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const margin = 8;
    const gap = 4;
    const width = Math.min(Math.max(rect.width, 220), viewportWidth - margin * 2);
    const left = Math.min(Math.max(rect.left, margin), viewportWidth - width - margin);
    const spaceBelow = viewportHeight - rect.bottom - margin;
    const spaceAbove = rect.top - margin;
    const openAbove = spaceBelow < 180 && spaceAbove > spaceBelow;
    const availableSpace = Math.max(openAbove ? spaceAbove : spaceBelow, 96);
    const maxHeight = Math.min(240, availableSpace - gap);
    const top = openAbove
      ? Math.max(margin, rect.top - maxHeight - gap)
      : Math.min(rect.bottom + gap, viewportHeight - margin - maxHeight);

    setDropdownStyle({
      left,
      top,
      width,
      maxHeight,
    });
  }, []);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    updateDropdownPosition();
    window.addEventListener('resize', updateDropdownPosition);
    window.addEventListener('scroll', updateDropdownPosition, true);

    return () => {
      window.removeEventListener('resize', updateDropdownPosition);
      window.removeEventListener('scroll', updateDropdownPosition, true);
    };
  }, [isOpen, updateDropdownPosition]);

  const toggleDropdown = () => {
    if (!isOpen) {
      updateDropdownPosition();
    }
    setIsOpen((current) => !current);
  };

  const toggleOption = (optionValue: string) => {
    const newValue = value.includes(optionValue)
      ? value.filter(v => v !== optionValue)
      : [...value, optionValue];
    onChange(newValue);
    window.requestAnimationFrame(updateDropdownPosition);
  };

  const removeOption = (optionValue: string) => {
    onChange(value.filter(v => v !== optionValue));
    window.requestAnimationFrame(updateDropdownPosition);
  };

  const selectedOptions = options.filter(option => value.includes(option.value));

  const dropdown = isOpen && dropdownStyle && typeof document !== 'undefined'
    ? createPortal(
        <>
          <div
            className="fixed inset-0 z-[60]"
            onClick={() => setIsOpen(false)}
          />
          <div
            className="fixed z-[70] overflow-y-auto rounded-xl border border-divider bg-background shadow-lg dark:border-divider dark:bg-foreground"
            style={dropdownStyle}
          >
            {options.map(option => {
              const isSelected = value.includes(option.value);
              return (
                <div
                  key={option.value}
                  className={`px-3 py-2 cursor-pointer transition-colors flex items-center justify-between hover:bg-foreground/70 dark:hover:bg-alt-foreground ${
                    isSelected ? 'bg-info/10' : ''
                  }`}
                  onClick={() => toggleOption(option.value)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-text dark:text-text truncate">
                      {option.label}
                    </div>
                    {option.subtitle && (
                      <div className="text-xs text-neutral-text dark:text-neutral-text truncate">
                        {option.subtitle}
                      </div>
                    )}
                  </div>
                  {isSelected && (
                    <Check className="w-4 h-4 text-info flex-shrink-0 ml-2" />
                  )}
                </div>
              );
            })}
            {options.length === 0 && (
              <div className="px-3 py-6 text-center text-neutral-text dark:text-neutral-text text-sm">
                No options available
              </div>
            )}
          </div>
        </>,
        document.body
      )
    : null;

  return (
    <div className={`relative min-w-0 ${className}`}>
      {/* Selected values display */}
      <div
        ref={triggerRef}
        className="input-modern min-h-[44px] min-w-0 flex flex-wrap gap-2 items-center overflow-hidden cursor-pointer"
        onClick={toggleDropdown}
      >
        {selectedOptions.length === 0 ? (
          <span className="min-w-0 flex-1 truncate text-neutral-text dark:text-neutral-text text-sm">{placeholder}</span>
        ) : (
          selectedOptions.map(option => (
            <div
              key={option.value}
              className="min-w-0 max-w-full rounded-lg border border-info/30 bg-info/15 px-2 py-1 text-sm text-info flex items-center gap-1"
              onClick={(e) => e.stopPropagation()}
            >
              <span className="min-w-0 truncate max-w-[120px]">{option.label}</span>
              <button
                type="button"
                onClick={() => removeOption(option.value)}
                className="flex-shrink-0 hover:bg-info/20 rounded p-0.5 transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))
        )}
        <ChevronDown
          className={`w-4 h-4 text-neutral-text dark:text-neutral-text ml-auto transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </div>

      {/* Dropdown */}
      {dropdown}
    </div>
  );
};

export default MultiSelect;
