import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";

describe("App", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders the HealthQuery shell after browser-session auth", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/api/auth/status")) return new Response(JSON.stringify({ enrolled: true }));
      if (path.endsWith("/api/auth/me")) return new Response(JSON.stringify({ authenticated: true }));
      return new Response(JSON.stringify({}), { status: 200 });
    }));
    render(<App />);
    expect(await screen.findByText("HealthQuery")).toBeInTheDocument();
    expect(await screen.findByText("Personal health dashboard")).toBeInTheDocument();
  });
});
