import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Unmount between tests. Without this, queries match elements left behind by an
// earlier test and failures point at the wrong thing.
afterEach(cleanup);
