/* Real-time ovozli suhbat — WebSocket klient yordamchisi.
   Bir xil origin: ws(s)://<host>/api/realtime/ws?avatar=<id>&voice=<v> */

export type RealtimeEvent = (type: string, data: Record<string, unknown>) => void;

export function openRealtimeWS(
  avatarId: string,
  voice: string,
  onEvent: RealtimeEvent,
  onOpen?: () => void,
  onClose?: () => void,
  lang?: string,
): WebSocket {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  // Base-prefiks (dev "", Spark "/avatar") — WS ham subpath ostidan o'tsin.
  const P = import.meta.env.BASE_URL.replace(/\/$/, "");
  const url =
    `${proto}://${location.host}${P}/api/realtime/ws` +
    `?avatar=${encodeURIComponent(avatarId)}&voice=${encodeURIComponent(voice)}` +
    (lang ? `&lang=${encodeURIComponent(lang)}` : "");
  const ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => onOpen?.();
  ws.onclose = () => onClose?.();
  ws.onmessage = (e) => {
    if (typeof e.data !== "string") return;
    try {
      const obj = JSON.parse(e.data) as { type: string };
      onEvent(obj.type, obj as Record<string, unknown>);
    } catch {
      /* ignore */
    }
  };
  return ws;
}
