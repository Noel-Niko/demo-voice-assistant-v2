import React from 'react';

interface ResizeHandleProps {
  onMouseDown: (e: React.MouseEvent) => void;
  isDragging: boolean;
}

/**
 * Draggable resize handle for panel width adjustment
 *
 * Features:
 * - 8px wide invisible hover area for easy targeting
 * - 2px visual indicator that appears on hover (grey) and during drag (blue)
 * - Smooth opacity transitions
 * - Positioned absolutely on the left edge of the right panel
 */
export const ResizeHandle: React.FC<ResizeHandleProps> = ({
  onMouseDown,
  isDragging,
}) => {
  const handleStyle: React.CSSProperties = {
    position: 'absolute',
    top: 0,
    left: 0,
    bottom: 0,
    width: '8px',
    cursor: 'col-resize',
    zIndex: 10,
    // Hover area (invisible but interactive)
    background: isDragging ? 'rgba(66, 133, 244, 0.2)' : 'transparent',
    transition: isDragging ? 'none' : 'background 0.15s ease',
  };

  const visualIndicatorStyle: React.CSSProperties = {
    position: 'absolute',
    top: 0,
    bottom: 0,
    left: '3px',
    width: '2px',
    background: isDragging ? '#4285f4' : 'rgba(0, 0, 0, 0.1)',
    borderRadius: '1px',
    opacity: isDragging ? 1 : 0,
    transition: 'opacity 0.15s ease',
  };

  const handleMouseEnter = (e: React.MouseEvent) => {
    const indicator = e.currentTarget.querySelector(
      '.resize-indicator'
    ) as HTMLElement;
    if (indicator && !isDragging) indicator.style.opacity = '0.6';
  };

  const handleMouseLeave = (e: React.MouseEvent) => {
    const indicator = e.currentTarget.querySelector(
      '.resize-indicator'
    ) as HTMLElement;
    if (indicator && !isDragging) indicator.style.opacity = '0';
  };

  return (
    <div
      style={handleStyle}
      onMouseDown={onMouseDown}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div className="resize-indicator" style={visualIndicatorStyle} />
    </div>
  );
};
