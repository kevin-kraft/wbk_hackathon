import { describe, it, expect, beforeEach, vi } from "vitest";
import { loadConfig } from "../config/runtime";
import { authHeaders, runStreamUrl } from "./api";

function mockConfig(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => body })),
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("API token wiring", () => {
  it("adds a Bearer header and ?token= when a token is set", async () => {
    mockConfig({ services: { orchestrator: "http://orch:8000" }, apiToken: "abc123" });
    await loadConfig();

    expect(authHeaders()).toEqual({ Authorization: "Bearer abc123" });
    const url = runStreamUrl(true, 0);
    expect(url).toContain("http://orch:8000/events/run");
    expect(url).toContain("token=abc123");
  });

  it("sends no token when none is configured", async () => {
    mockConfig({ services: { orchestrator: "http://orch:8000" } });
    await loadConfig();

    expect(authHeaders()).toEqual({});
    expect(runStreamUrl(true, 0)).not.toContain("token=");
  });

  it("url-encodes the token in the stream URL", async () => {
    mockConfig({ services: { orchestrator: "http://orch:8000" }, apiToken: "a b/c" });
    await loadConfig();

    expect(runStreamUrl(true, 0)).toContain("token=a%20b%2Fc");
  });
});
