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
  // WS ROOT yo'lda (base-prefiksсиз): /api/ws/avatar/realtime. Lokalda to'g'ridan
  // backendga; Spark'da nginx `location /api/ws/avatar/` (WS upgrade bilan) orqali —
  // /avatar/api/ HTTP location'idan alohida (upgrade muammosini chetlab o'tadi).
  const url =
    `${proto}://${location.host}/api/ws/avatar/realtime` +
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
