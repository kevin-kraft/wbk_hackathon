import { describe, it, expect } from "vitest";
import { STAGES, STAGE_INDEX, stateToStage, stateStyle } from "./stages";

describe("stateToStage", () => {
  it("maps each loop state onto the right pipeline stage", () => {
    expect(stateToStage("LOCATE")).toBe("LOCATE");
    expect(stateToStage("POSE")).toBe("POSE");
    expect(stateToStage("GRIP")).toBe("GRASP");
    expect(stateToStage("REGRASP")).toBe("GRASP");
    expect(stateToStage("SKIP")).toBe("GRASP");
    expect(stateToStage("REMOVE")).toBe("REMOVE");
    expect(stateToStage("RECHECK")).toBe("REMOVE");
    expect(stateToStage("SORT")).toBe("SORT");
  });

  it("returns null for terminal / non-stage states", () => {
    expect(stateToStage("DONE")).toBeNull();
    expect(stateToStage("BLOCKED")).toBeNull();
    expect(stateToStage("SUMMARY")).toBeNull();
    expect(stateToStage("SOMETHING_ELSE")).toBeNull();
  });

  it("every mapped stage exists in STAGES", () => {
    for (const s of ["LOCATE", "POSE", "GRIP", "REGRASP", "REMOVE", "SORT"]) {
      const stage = stateToStage(s);
      expect(stage).not.toBeNull();
      expect(STAGE_INDEX[stage!]).toBeTypeOf("number");
    }
  });
});

describe("STAGES", () => {
  it("is the canonical 7-stage order", () => {
    expect(STAGES.map((s) => s.key)).toEqual([
      "LOCATE",
      "POSE",
      "PLAN",
      "GRASP",
      "REMOVE",
      "INSPECT",
      "SORT",
    ]);
  });
});

describe("stateStyle", () => {
  it("returns a known style for a known state and a fallback otherwise", () => {
    expect(stateStyle("LOCATE")).toContain("sky");
    expect(stateStyle("NOPE")).toContain("zinc");
  });
});
