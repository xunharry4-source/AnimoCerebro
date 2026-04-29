import "@testing-library/jest-dom/vitest";

// MUI X DataGrid relies on ResizeObserver in the browser.
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

global.ResizeObserver = global.ResizeObserver || ResizeObserverMock;
