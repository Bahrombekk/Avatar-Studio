import { describe, it, expect } from "vitest";
import { screenToPath, pathToRoute } from "./navigation";

describe("screenToPath", () => {
  it("maps screens to URLs", () => {
    expect(screenToPath({ screen: "dashboard" })).toBe("/admin");
    expect(screenToPath({ screen: "analytics" })).toBe("/admin/analytics");
    expect(screenToPath({ screen: "studio" })).toBe("/admin/studio");
    expect(screenToPath({ screen: "canned" })).toBe("/admin/canned");
    expect(screenToPath({ screen: "realtime" })).toBe("/");
    expect(screenToPath({ screen: "editor", id: "abc" })).toBe(
      "/admin/editor/abc",
    );
    expect(screenToPath({ screen: "editor" })).toBe("/admin/editor/new");
    expect(screenToPath({ screen: "preview", id: "x" })).toBe(
      "/admin/preview/x",
    );
    expect(screenToPath({ screen: "preview" })).toBe("/admin/preview");
    expect(screenToPath({ screen: "noma'lum" })).toBe("/admin"); // default
  });
});

describe("pathToRoute", () => {
  it("maps URLs back to {screen,id}", () => {
    expect(pathToRoute("/")).toEqual({ screen: "realtime" });
    expect(pathToRoute("")).toEqual({ screen: "realtime" });
    expect(pathToRoute("/admin")).toEqual({ screen: "dashboard" });
    expect(pathToRoute("/admin/analytics")).toEqual({ screen: "analytics" });
    expect(pathToRoute("/admin/editor/abc")).toEqual({
      screen: "editor",
      id: "abc",
    });
    expect(pathToRoute("/admin/preview/x")).toEqual({ screen: "preview" });
  });

  it("round-trips for stable screens", () => {
    for (const screen of ["analytics", "studio", "canned", "settings"]) {
      expect(pathToRoute(screenToPath({ screen })).screen).toBe(screen);
    }
  });
});
