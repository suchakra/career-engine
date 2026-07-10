import { setupServer } from "msw/node";

import { handlers } from "./handlers";

/** The shared MSW server for network-free tests (started in vitest.setup.ts). */
export const server = setupServer(...handlers);
