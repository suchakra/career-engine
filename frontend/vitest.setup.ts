import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { cleanup } from "@testing-library/react";

import { server } from "./src/test/msw/server";

// Start the MSW mock server once; reset handlers between tests so per-test
// overrides (e.g. a 500 to exercise rollback) never leak. Tests are network-free.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
