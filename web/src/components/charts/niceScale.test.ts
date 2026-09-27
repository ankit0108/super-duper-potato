import { niceScale } from "./Charts";

describe("niceScale", () => {
  it.each([
    [15, true, [0, 5, 10, 15]],
    [8, true, [0, 2, 4, 6, 8]],
    [7, true, [0, 2, 4, 6, 8]],
    [1, true, [0, 1]],
    [0, true, [0, 1]],
    [3, true, [0, 1, 2, 3]],
    [0.232, false, [0, 0.1, 0.2, 0.3]],
    [0.45, false, [0, 0.2, 0.4, 0.6]],
    [3188, true, [0, 1000, 2000, 3000, 4000]],
  ])("max %s (integers: %s)", (max, integer, ticks) => {
    const s = niceScale(max, integer);
    expect(s.ticks).toEqual(ticks);
    expect(s.max).toBe(ticks[ticks.length - 1]);
    expect(s.max).toBeGreaterThanOrEqual(max);
  });
});
