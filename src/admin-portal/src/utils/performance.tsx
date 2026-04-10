/**
 * Performance Optimization Utilities for React Components
 * 
 * Purpose:
 *     Provides utility functions and higher-order components for optimizing
 *     React component performance through memoization, lazy loading, and
 *     efficient rendering strategies.
 *     
 * Responsibilities:
 *     - Component memoization wrappers
 *     - Lazy loading with error boundaries
 *     - Virtual scrolling utilities
 *     - Render optimization helpers
 *     - Performance monitoring
 *     
 * Not Responsible For:
 *     - State management logic
 *     - API data fetching
 *     - Business logic implementation
 */

import React, { useMemo, useCallback, Suspense, lazy, Component, ErrorInfo, ReactNode } from 'react';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function debounce<T extends (...args: any[]) => any>(func: T, wait: number): T {
  let timeout: ReturnType<typeof setTimeout> | null = null;
  
  return ((...args: Parameters<T>) => {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  }) as T;
}

/**
 * Memoize a component with custom comparison function
 * 
 * @param Component - React component to memoize
 * @param areEqual - Custom equality check function
 * @returns Memoized component
 */
export function memoWithComparison<P extends object>(
  Component: React.ComponentType<P>,
  areEqual?: (prevProps: Readonly<P>, nextProps: Readonly<P>) => boolean
): React.MemoExoticComponent<React.ComponentType<P>> {
  return React.memo(Component, areEqual);
}

/**
 * Create a lazy-loaded component with fallback and error boundary
 * 
 * @param importFn - Dynamic import function
 * @param fallback - Fallback component while loading
 * @returns Lazy-loaded component wrapped in Suspense
 */
export function createLazyComponent<P extends object>(
  importFn: () => Promise<{ default: React.ComponentType<P> }>,
  fallback: ReactNode = <div>Loading...</div>
): React.FC<P> {
  const LazyComponent = lazy(importFn);
  
  const LazyWrapper: React.FC<P> = (props) => (
    <Suspense fallback={fallback}>
      <LazyComponent {...props} />
    </Suspense>
  );
  
  LazyWrapper.displayName = `LazyComponent(${importFn.toString().slice(0, 30)}...)`;
  
  return LazyWrapper;
}

/**
 * Error Boundary Component
 * Catches errors in child component tree and displays fallback UI
 */
interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.props.onError?.(error, errorInfo);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      // eslint-disable-next-line react/jsx-no-useless-fragment
      return <>{this.props.fallback || (
        <div style={{ padding: '20px', color: 'red' }}>
          <h3>Something went wrong</h3>
          <p>{this.state.error?.message}</p>
        </div>
      )}</>;
    }

    return this.props.children;
  }
}

/**
 * Optimize list rendering with virtualization hints
 * Returns optimized props for list items
 * 
 * @param itemCount - Total number of items
 * @param itemSize - Estimated item size in pixels
 * @returns Optimization configuration
 */
export function optimizeListRendering(itemCount: number, itemSize: number = 50) {
  const shouldVirtualize = itemCount > 100;
  
  return {
    shouldVirtualize,
    estimatedItemSize: itemSize,
    recommendedLibrary: shouldVirtualize ? 'react-window' : 'native',
    bufferSize: Math.min(10, Math.floor(itemCount * 0.1)),
  };
}

/**
 * Debounce callback for performance optimization
 * 
 * @param func - Function to debounce
 * @param delay - Delay in milliseconds
 * @returns Debounced callback
 */
export function useDebouncedCallback<T extends (...args: any[]) => any>(
  func: T,
  delay: number = 300
): T {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useCallback(
    debounce(func, delay) as T,
    [func, delay]
  );
}

/**
 * Simple throttle implementation
 */
function throttle<T extends (...args: any[]) => any>(func: T, limit: number): T {
  let inThrottle = false;
  
  return ((...args: Parameters<T>) => {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  }) as T;
}

/**
 * Performance monitoring hook
 * Tracks render count and timing
 * 
 * @param componentName - Name of component being monitored
 * @returns Performance metrics
 */
export function usePerformanceMonitor(componentName: string) {
  const renderCount = React.useRef(0);
  const lastRenderTime = React.useRef<number>(Date.now());
  
  renderCount.current += 1;
  const currentTime = Date.now();
  const timeSinceLastRender = currentTime - lastRenderTime.current;
  lastRenderTime.current = currentTime;
  
  // Log in development mode
  // eslint-disable-next-line no-restricted-globals
  const isDev = typeof process !== 'undefined' && process.env?.NODE_ENV === 'development';
  if (isDev) {
    console.debug(
      `[Perf] ${componentName}:`,
      `Render #${renderCount.current},`,
      `Time since last: ${timeSinceLastRender}ms`
    );
  }
  
  return {
    renderCount: renderCount.current,
    timeSinceLastRender,
  };
}

/**
 * Optimize expensive calculations with memoization
 * 
 * @param calculation - Expensive calculation function
 * @param dependencies - Dependencies array
 * @returns Memoized result
 */
export function useOptimizedCalculation<T>(
  calculation: () => T,
  dependencies: React.DependencyList
): T {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(calculation, dependencies);
}

/**
 * Batch multiple state updates
 * Useful for preventing excessive re-renders
 * 
 * @param updates - Array of update functions
 */
export function batchUpdates(updates: Array<() => void>): void {
  // In React 18+, setState is automatically batched
  // This is a compatibility wrapper
  updates.forEach(update => update());
}

/**
 * Check if component should re-render based on prop changes
 * 
 * @param prevProps - Previous props
 * @param nextProps - Next props
 * @param keysToCompare - Specific keys to compare (optional)
 * @returns True if props are equal (should NOT re-render)
 */
export function shallowCompare<P extends object>(
  prevProps: P,
  nextProps: P,
  keysToCompare?: (keyof P)[]
): boolean {
  const keys = keysToCompare || (Object.keys(prevProps) as (keyof P)[]);
  
  for (const key of keys) {
    if (prevProps[key] !== nextProps[key]) {
      return false;
    }
  }
  
  return true;
}
