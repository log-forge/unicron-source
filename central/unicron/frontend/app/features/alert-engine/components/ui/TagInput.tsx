import React, { useState, useRef } from 'react';
import { X, Plus } from 'lucide-react';

interface TagInputProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
  predefinedTags?: string[];
  className?: string;
  helpText?: string;
  helpRight?: React.ReactNode;
}

const TagInput: React.FC<TagInputProps> = ({
  tags,
  onChange,
  placeholder = "Add tags...",
  predefinedTags = [],
  className = "",
  helpText,
  helpRight
}) => {
  const [inputValue, setInputValue] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Filter predefined tags that aren't already selected
  const availablePredefined = predefinedTags.filter(tag => !tags.includes(tag));
  const filteredSuggestions = availablePredefined.filter(tag =>
    tag.toLowerCase().includes(inputValue.toLowerCase())
  );

  const addTag = (tag: string) => {
    const trimmedTag = tag.trim();
    if (trimmedTag && !tags.includes(trimmedTag)) {
      onChange([...tags, trimmedTag]);
    }
    setInputValue('');
    setShowSuggestions(false);
  };

  const removeTag = (tagToRemove: string) => {
    onChange(tags.filter(tag => tag !== tagToRemove));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      if (inputValue.trim()) {
        addTag(inputValue);
      }
    } else if (e.key === 'Backspace' && !inputValue && tags.length > 0) {
      removeTag(tags[tags.length - 1]);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setInputValue(value);
    setShowSuggestions(value.length > 0 && filteredSuggestions.length > 0);
  };

  const tagColors = [
    'bg-info/10 text-info dark:bg-info/50 dark:text-info',
    'bg-success/10 text-success dark:bg-success/50 dark:text-success',
    'bg-primary/10 text-primary dark:bg-primary/50 dark:text-primary',
    'bg-error/10 text-error dark:bg-error/50 dark:text-error',
    'bg-warning/10 text-warning dark:bg-warning/40 dark:text-warning',
    'bg-primary/10 text-primary dark:bg-primary/50 dark:text-primary',
    'bg-alt-foreground text-text dark:bg-alt-foreground dark:text-text'
  ];

  const getTagColor = (index: number) => {
    return tagColors[index % tagColors.length];
  };

  return (
    <div className={`relative ${className}`}>
      {/* Tags and input container */}
      <div className="input-modern min-h-[44px] flex flex-wrap items-center gap-2 cursor-text">
        {/* Existing tags */}
        {tags.map((tag, index) => (
          <span
            key={tag}
            className={`inline-flex items-center px-2 py-1 text-xs rounded-full ${getTagColor(index)}`}
          >
            {tag}
            <button
              type="button"
              onClick={() => removeTag(tag)}
              className="ml-1 hover:bg-neutral/20 dark:hover:bg-neutral/20 rounded-full p-0.5"
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}

        {/* Input field */}
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => setShowSuggestions(inputValue.length > 0 && filteredSuggestions.length > 0)}
          onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
          placeholder={tags.length === 0 ? placeholder : ""}
          className="flex-1 min-w-[120px] outline-none text-sm bg-transparent text-text dark:text-text placeholder:text-neutral-text"
        />
      </div>

      {/* Suggestions dropdown */}
      {showSuggestions && filteredSuggestions.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-background dark:bg-foreground border border-divider dark:border-divider rounded-md shadow-lg z-10 max-h-40 overflow-y-auto">
          {filteredSuggestions.map(tag => (
            <button
              key={tag}
              type="button"
              onClick={() => addTag(tag)}
              className="w-full text-left px-3 py-2 hover:bg-alt-foreground dark:hover:bg-alt-foreground text-sm flex items-center text-text dark:text-text"
            >
              <Plus className="w-3 h-3 mr-2 text-neutral-text dark:text-neutral-text" />
              {tag}
            </button>
          ))}
        </div>
      )}

      {/* Help / footer */}
      <div className="text-xs text-neutral-text mt-1 flex items-center justify-between">
        <span>{helpText || 'Type and press Enter or comma to add tags'}</span>
        {helpRight && <span className="text-neutral-text">{helpRight}</span>}
      </div>
    </div>
  );
};

export default TagInput;
