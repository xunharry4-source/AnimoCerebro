/**
 * Unit tests for Performance Optimization Utilities.
 * 
 * Test Categories:
 *     - Normal: Memoization, lazy loading, error boundaries
 *     - Abnormal: Error handling, edge cases
 *     - Edge: Empty lists, rapid updates
 * 
 * Realism Label: logic_analysis (tests written, execution pending)
 */

import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import React from 'react';
import {
  memoWithComparison,
  createLazyComponent,
  ErrorBoundary,
  withErrorBoundary,
  optimizeListRendering,
  useDebouncedCallback,
  useThrottledCallback,
  usePerformanceMonitor,
  useOptimizedCalculation,
  shallowCompare,
} from '../performance';

describe('Performance Utilities', () => {
  describe('memoWithComparison', () => {
    it('should create memoized component', () => {
      const TestComponent = ({ value }: { value: number }) => <div>{value}</div>;
      const MemoizedComponent = memoWithComparison(TestComponent);
      
      expect(MemoizedComponent).toBeDefined();
    });

    it('should use custom comparison function', () => {
      let renderCount = 0;
      const TestComponent = ({ value }: { value: number }) => {
        renderCount++;
        return <div data-testid="test">{value}</div>;
      };
      
      const areEqual = (prev: any, next: any) => prev.value === next.value;
      const MemoizedComponent = memoWithComparison(TestComponent, areEqual);
      
      const { rerender } = render(<MemoizedComponent value={1} />);
      rerender(<MemoizedComponent value={1} />);
      
      // Should only render once due to memoization
      expect(renderCount).toBe(1);
    });
  });

  describe('optimizeListRendering', () => {
    it('should recommend virtualization for large lists', () => {
      const config = optimizeListRendering(200, 50);
      
      expect(config.shouldVirtualize).toBe(true);
      expect(config.recommendedLibrary).toBe('react-window');
      expect(config.estimatedItemSize).toBe(50);
    });

    it('should not recommend virtualization for small lists', () => {
      const config = optimizeListRendering(50, 50);
      
      expect(config.shouldVirtualize).toBe(false);
      expect(config.recommendedLibrary).toBe('native');
    });

    it('should calculate appropriate buffer size', () => {
      const config = optimizeListRendering(1000, 50);
      
      expect(config.bufferSize).toBe(10); // Min of 10 and 100
    });
  });

  describe('shallowCompare', () => {
    it('should detect equal props', () => {
      const prevProps = { a: 1, b: 'test', c: true };
      const nextProps = { a: 1, b: 'test', c: true };
      
      expect(shallowCompare(prevProps, nextProps)).toBe(true);
    });

    it('should detect different props', () => {
      const prevProps = { a: 1, b: 'test' };
      const nextProps = { a: 2, b: 'test' };
      
      expect(shallowCompare(prevProps, nextProps)).toBe(false);
    });

    it('should compare specific keys only', () => {
      const prevProps = { a: 1, b: 'test', c: true };
      const nextProps = { a: 1, b: 'changed', c: false };
      
      // Only compare 'a'
      expect(shallowCompare(prevProps, nextProps, ['a'])).toBe(true);
      
      // Compare 'a' and 'b'
      expect(shallowCompare(prevProps, nextProps, ['a', 'b'])).toBe(false);
    });
  });

  describe('ErrorBoundary', () => {
    it('should render children when no error', () => {
      render(
        <ErrorBoundary>
          <div data-testid="child">Child Content</div>
        </ErrorBoundary>
      );
      
      expect(screen.getByTestId('child')).toBeInTheDocument();
    });

    it('should show fallback on error', () => {
      const ErrorComponent = () => {
        throw new Error('Test error');
      };

      render(
        <ErrorBoundary fallback={<div data-testid="fallback">Error occurred</div>}>
          <ErrorComponent />
        </ErrorBoundary>
      );
      
      expect(screen.getByTestId('fallback')).toBeInTheDocument();
    });

    it('should call onError callback', () => {
      let errorCaptured = false;
      const onError = () => { errorCaptured = true; };
      const ErrorComponent = () => {
        throw new Error('Test error');
      };

      render(
        <ErrorBoundary onError={onError}>
          <ErrorComponent />
        </ErrorBoundary>
      );
      
      expect(errorCaptured).toBe(true);
    });
  });

  describe('withErrorBoundary', () => {
    it('should wrap component with error boundary', () => {
      const TestComponent = () => <div data-testid="wrapped">Content</div>;
      const WrappedComponent = withErrorBoundary(TestComponent);
      
      render(<WrappedComponent />);
      
      expect(screen.getByTestId('wrapped')).toBeInTheDocument();
    });

    it('should use custom fallback', () => {
      const ErrorComponent = () => {
        throw new Error('Test error');
      };
      const WrappedComponent = withErrorBoundary(
        ErrorComponent,
        <div data-testid="custom-fallback">Custom Error</div>
      );
      
      render(<WrappedComponent />);
      
      expect(screen.getByTestId('custom-fallback')).toBeInTheDocument();
    });
  });

  describe('useDebouncedCallback', () => {
    it('should create debounced callback function', () => {
      let callCount = 0;
      const mockFn = () => { callCount++; };
      
      const TestComponent = () => {
        const debouncedFn = useDebouncedCallback(mockFn, 300);
        return <button onClick={() => debouncedFn()}>Click</button>;
      };
      
      render(<TestComponent />);
      const button = screen.getByText('Click');
      
      // Should be able to click without errors
      expect(() => button.click()).not.toThrow();
    });
  });

  describe('useThrottledCallback', () => {
    it('should create throttled callback function', () => {
      let callCount = 0;
      const mockFn = () => { callCount++; };
      
      const TestComponent = () => {
        const throttledFn = useThrottledCallback(mockFn, 200);
        return <button onClick={() => throttledFn()}>Click</button>;
      };
      
      render(<TestComponent />);
      const button = screen.getByText('Click');
      
      // Should be able to click without errors
      expect(() => button.click()).not.toThrow();
    });
  });

  describe('usePerformanceMonitor', () => {
    it('should track render count', () => {
      let capturedMetrics: any;
      
      const TestComponent = () => {
        const metrics = usePerformanceMonitor('TestComponent');
        capturedMetrics = metrics;
        return <div>Test</div>;
      };
      
      const { rerender } = render(<TestComponent />);
      rerender(<TestComponent />);
      
      expect(capturedMetrics.renderCount).toBe(2);
    });
  });

  describe('useOptimizedCalculation', () => {
    it('should memoize expensive calculations', () => {
      let calculationCount = 0;
      
      const TestComponent = ({ value }: { value: number }) => {
        const result = useOptimizedCalculation(() => {
          calculationCount++;
          return value * 2;
        }, [value]);
        
        return <div data-testid="result">{result}</div>;
      };
      
      const { rerender } = render(<TestComponent value={5} />);
      expect(calculationCount).toBe(1);
      
      // Re-render with same value
      rerender(<TestComponent value={5} />);
      expect(calculationCount).toBe(1); // Should not recalculate
      
      // Re-render with different value
      rerender(<TestComponent value={10} />);
      expect(calculationCount).toBe(2); // Should recalculate
    });
  });

  describe('createLazyComponent', () => {
    it('should create lazy component wrapper', async () => {
      const mockImport = () => 
        Promise.resolve({ default: () => <div>Lazy Component</div> });
      
      const LazyComponent = createLazyComponent(mockImport);
      
      expect(LazyComponent).toBeDefined();
      expect(LazyComponent.displayName).toContain('LazyComponent');
    });
  });
});

describe('Performance Utilities - Edge Cases', () => {
  describe('optimizeListRendering edge cases', () => {
    it('should handle zero items', () => {
      const config = optimizeListRendering(0, 50);
      
      expect(config.shouldVirtualize).toBe(false);
      expect(config.bufferSize).toBe(0);
    });

    it('should handle negative item count', () => {
      const config = optimizeListRendering(-10, 50);
      
      expect(config.shouldVirtualize).toBe(false);
    });

    it('should handle very large lists', () => {
      const config = optimizeListRendering(100000, 50);
      
      expect(config.shouldVirtualize).toBe(true);
      expect(config.bufferSize).toBe(10); // Capped at 10
    });
  });

  describe('shallowCompare edge cases', () => {
    it('should handle empty objects', () => {
      expect(shallowCompare({}, {})).toBe(true);
    });

    it('should handle null/undefined values', () => {
      const prevProps: any = { a: null, b: undefined };
      const nextProps: any = { a: null, b: undefined };
      
      expect(shallowCompare(prevProps, nextProps)).toBe(true);
    });

    it('should handle object references', () => {
      const obj = { key: 'value' };
      const prevProps = { data: obj };
      const nextProps = { data: obj };
      
      expect(shallowCompare(prevProps, nextProps)).toBe(true);
    });
  });

  describe('ErrorBoundary edge cases', () => {
    it('should handle nested errors', () => {
      const DeepErrorComponent = () => {
        throw new Error('Deep error');
      };

      render(
        <ErrorBoundary fallback={<div data-testid="fallback">Error</div>}>
          <div>
            <DeepErrorComponent />
          </div>
        </ErrorBoundary>
      );
      
      expect(screen.getByTestId('fallback')).toBeInTheDocument();
    });
  });
});
