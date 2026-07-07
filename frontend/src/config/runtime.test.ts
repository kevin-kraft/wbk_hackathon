import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  loadConfig,
  serviceUrl,
  streamUrl,
  getOverrides,
  saveOverrides,
  clearOverrides,
} from "./runtime";

function mockConfigJson(body: unknown, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok, json: async () => body })),
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("loadConfig precedence", () => {
  it("applies config.json over the localhost defaults and strips trailing slashes", async () => {
    mockConfigJson({
      services: { orchestrator: "http://svc:9000/" },
      streams: { sceneCamera: "http://cam:8080/s/" },
    });

    await loadConfig();

    expect(serviceUrl("orchestrator")).toBe("http://svc:9000");
    expect(streamUrl("sceneCamera")).toBe("http://cam:8080/s");
    // A key not present in config.json keeps its default.
    expect(serviceUrl("yolo")).toBe("http://localhost:8001");
  });

  it("lets a localStorage override win over config.json", async () => {
    saveOverrides({ services: { orchestrator: "http://override:1" } as never });
    mockConfigJson({ services: { orchestrator: "http://svc:9000" } });

    await loadConfig();

    expect(serviceUrl("orchestrator")).toBe("http://override:1");
  });

  it("falls back to localhost defaults when config.json is missing", async () => {
    mockConfigJson({}, false); // non-ok response -> ignored

    await loadConfig();

    expect(serviceUrl("yolo")).toBe("http://localhost:8001");
    expect(serviceUrl("damage")).toBe("http://localhost:8006");
  });

  it("survives a fetch rejection", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network down");
      }),
    );

    await loadConfig();

    expect(serviceUrl("orchestrator")).toBe("http://localhost:8000");
  });
});

describe("overrides storage", () => {
  it("round-trips saveOverrides / getOverrides and clears", () => {
    expect(getOverrides()).toBeNull();

    const patch = { run: { dryRun: false, stepDelayMs: 250 } };
    saveOverrides(patch);
    expect(getOverrides()).toEqual(patch);

    clearOverrides();
    expect(getOverrides()).toBeNull();
  });

  it("returns null on corrupt override JSON", () => {
    localStorage.setItem("wbk.config.overrides", "{not json");
    expect(getOverrides()).toBeNull();
  });
});
