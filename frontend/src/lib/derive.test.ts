import { describe, it, expect } from "vitest";
import type { LoopEvent, RunStats } from "./types";
import { tallyBins, deriveInspections, deriveGrip, currentPart, derivePlan } from "./derive";

function ev(step: number, state: string, data: Record<string, unknown> = {}): LoopEvent {
  return { step, state, message: `${state} ${step}`, data };
}

// Mirrors the mock dry-run: cover (retry then ok), bracket (ok), gear (damaged).
const RUN: LoopEvent[] = [
  ev(1, "LOCATE", { part: "cover" }),
  ev(1, "POSE"),
  ev(1, "REGRASP", { attempt: 1 }),
  ev(1, "GRIP"),
  ev(1, "REMOVE"),
  ev(1, "SORT", { verdict: "ok", bin: "ok_bin" }),
  ev(2, "LOCATE", { part: "bracket" }),
  ev(2, "GRIP"),
  ev(2, "SORT", { verdict: "ok", bin: "ok_bin" }),
  ev(3, "LOCATE", { part: "gear" }),
  ev(3, "GRIP"),
  ev(3, "SORT", { verdict: "damaged", bin: "reject_bin" }),
];

describe("tallyBins", () => {
  it("counts bins from SORT events when there's no summary yet", () => {
    expect(tallyBins(RUN, null)).toEqual({ removed: 3, ok: 2, reject: 1, skipped: 0 });
  });

  it("prefers the final summary stats over the live count", () => {
    const stats: RunStats = { removed: 9, ok_bin: 5, reject_bin: 4, skipped: 2 };
    expect(tallyBins(RUN, stats)).toEqual({ removed: 9, ok: 5, reject: 4, skipped: 2 });
  });

  it("counts SKIP events as skipped", () => {
    const withSkip = [...RUN, ev(4, "SKIP", { part: "stuck" })];
    expect(tallyBins(withSkip, null).skipped).toBe(1);
  });

  it("is empty for no events", () => {
    expect(tallyBins([], null)).toEqual({ removed: 0, ok: 0, reject: 0, skipped: 0 });
  });
});

describe("deriveInspections", () => {
  it("pairs each SORT with its step's located part", () => {
    expect(deriveInspections(RUN)).toEqual([
      { step: 1, part: "cover", verdict: "ok", bin: "ok_bin" },
      { step: 2, part: "bracket", verdict: "ok", bin: "ok_bin" },
      { step: 3, part: "gear", verdict: "damaged", bin: "reject_bin" },
    ]);
  });

  it("is empty before any SORT", () => {
    expect(deriveInspections([ev(1, "LOCATE", { part: "cover" })])).toEqual([]);
  });
});

describe("deriveGrip", () => {
  it("scopes to the current part and reports a confirmed grasp", () => {
    // Full RUN => current part is gear (step 3), grasped on first try.
    expect(deriveGrip(RUN)).toEqual({ attempts: 0, confirmed: true, retrying: false, status: "grasped" });
  });

  it("counts retries within the current part", () => {
    const upToFirstGrip = RUN.slice(0, 4); // LOCATE, POSE, REGRASP, GRIP  (cover)
    const g = deriveGrip(upToFirstGrip);
    expect(g.attempts).toBe(1);
    expect(g.confirmed).toBe(true);
    expect(g.status).toBe("grasped");
  });

  it("reports regrasping when the latest event is a retry", () => {
    const midRetry = RUN.slice(0, 3); // LOCATE, POSE, REGRASP
    expect(deriveGrip(midRetry)).toMatchObject({ retrying: true, confirmed: false, status: "regrasping" });
  });

  it("is idle for no events", () => {
    expect(deriveGrip([])).toEqual({ attempts: 0, confirmed: false, retrying: false, status: "idle" });
  });
});

describe("currentPart", () => {
  it("returns the latest located part + step", () => {
    expect(currentPart(RUN)).toEqual({ part: "gear", step: 3 });
  });

  it("falls back to a placeholder with no events", () => {
    expect(currentPart([])).toEqual({ part: "—", step: 0 });
  });
});

describe("derivePlan", () => {
  const PLAN_RUN: LoopEvent[] = [
    ev(0, "PLAN_GENERATED", {
      product: "gearbox-demo",
      source: "mock",
      steps: [
        { part: "cover", action: "lift the top cover" },
        { part: "bracket", action: "slide the bracket out" },
        { part: "gear", action: "pull the gear off" },
      ],
    }),
    ev(1, "STEP", { part: "cover", index: 1, total: 3 }),
    ev(1, "LOCATE", { part: "cover" }),
    ev(1, "SORT", { verdict: "ok", bin: "ok_bin" }),
    ev(2, "STEP", { part: "bracket", index: 2, total: 3 }),
  ];

  it("returns null for a run without a plan", () => {
    expect(derivePlan(RUN)).toBeNull();
  });

  it("marks completed steps done and the current step active", () => {
    const plan = derivePlan(PLAN_RUN);
    expect(plan?.source).toBe("mock");
    expect(plan?.rows.map((r) => r.status)).toEqual(["done", "active", "pending"]);
  });

  it("marks a blocked step blocked", () => {
    const blocked = [...PLAN_RUN, ev(2, "SKIP", {}), ev(2, "BLOCKED", {})];
    expect(derivePlan(blocked)?.rows[1].status).toBe("blocked");
  });

  it("marks a step whose part was missing from the scene as skipped", () => {
    const skipped = [...PLAN_RUN, ev(2, "SKIP", { part: "bracket" }), ev(3, "STEP", { part: "gear", index: 3, total: 3 })];
    expect(derivePlan(skipped)?.rows.map((r) => r.status)).toEqual(["done", "skipped", "active"]);
  });
});
