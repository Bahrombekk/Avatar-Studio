import { describe, it, expect } from "vitest";
import { translate, LANGS } from "./index";

describe("translate", () => {
  it("returns language-specific string", () => {
    expect(translate("uz", "rt.speak")).toBe("Gapirish");
    expect(translate("ru", "rt.speak")).toBe("Говорить");
    expect(translate("en", "rt.speak")).toBe("Speak");
  });

  it("falls back to uz, then key, then provided fallback", () => {
    // Mavjud bo'lmagan kalit + fallback berilgan
    expect(translate("en", "yoq.kalit", "FB")).toBe("FB");
    // fallback'siz → kalitning o'zi
    expect(translate("en", "yoq.kalit")).toBe("yoq.kalit");
  });

  it("exposes three languages", () => {
    expect(LANGS.map((l) => l.id)).toEqual(["uz", "ru", "en"]);
  });
});
