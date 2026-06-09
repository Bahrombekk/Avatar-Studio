import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { API, getToken, setToken, clearToken } from "./client";

function streamResponse(chunks: string[]): Response {
  const enc = new TextEncoder();
  let i = 0;
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(enc.encode(chunks[i++]));
      } else {
        controller.close();
      }
    },
  });
  return new Response(body, { status: 200 });
}

describe("token storage", () => {
  beforeEach(() => clearToken());
  it("set/get/clear round-trip", () => {
    expect(getToken()).toBe("");
    setToken("abc123");
    expect(getToken()).toBe("abc123");
    clearToken();
    expect(getToken()).toBe("");
  });
});

describe("API.login", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("stores token on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ token: "tok" }), { status: 200 }),
      ),
    );
    const t = await API.login("pw");
    expect(t).toBe("tok");
    expect(getToken()).toBe("tok");
  });
  it("throws detail message on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "Parol noto'g'ri" }), {
            status: 401,
          }),
      ),
    );
    await expect(API.login("bad")).rejects.toThrow("Parol noto'g'ri");
  });
});

describe("API.chatStream (SSE)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("parses events split across chunk boundaries", async () => {
    // 'text' eventi ikki o'qish orasida bo'linadi; 'video' to'liq keladi.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        streamResponse([
          'data: {"type":"text","text":"Sal',
          'om"}\n\ndata: {"type":"video","url":"/v.mp4"}\n\n',
          "data: notjson\n\n", // buzilgan — e'tiborsiz
        ]),
      ),
    );
    const events: Array<{ type: string; data: any }> = [];
    await API.chatStream("salom", "av_x", "madina", (type, data) =>
      events.push({ type, data }),
    );
    expect(events.map((e) => e.type)).toEqual(["text", "video"]);
    expect(events[0].data.text).toBe("Salom");
    expect(events[1].data.url).toBe("/v.mp4");
  });

  it("throws when body missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 200 })),
    );
    await expect(API.chatStream("x", "a", "v", () => {})).rejects.toThrow();
  });
});

describe("API.voices", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("extracts voices array from {default, voices}", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ default: "madina", voices: [{ id: "madina" }] }),
            { status: 200 },
          ),
      ),
    );
    const v = await API.voices();
    expect(v).toHaveLength(1);
    expect(v[0].id).toBe("madina");
  });
});
