/* Eski {screen,id} navigatsiya API'si ↔ react-router URL ko'prigi.
   Admin sahifalar endi /admin ostida; public real-time / da. */
import { useNavigate } from "react-router-dom";

export interface Route {
  screen: string;
  id?: string;
}

/** {screen,id} → URL yo'li. Admin sahifalar /admin prefiksi bilan. */
export function screenToPath(route: Route): string {
  switch (route.screen) {
    case "dashboard":
      return "/admin";
    case "editor":
      return "/admin/editor/" + (route.id || "new");
    case "analytics":
      return "/admin/analytics";
    case "studio":
      return "/admin/studio";
    case "conversations":
      return "/admin/conversations";
    case "users":
      return "/admin/users";
    case "settings":
      return "/admin/settings";
    case "preview":
      return route.id ? "/admin/preview/" + route.id : "/admin/preview";
    case "realtime":
      return "/"; // public foydalanuvchi sahifasi
    default:
      return "/admin";
  }
}

/** URL yo'li → {screen,id} (Sidebar'ning active holati uchun). */
export function pathToRoute(pathname: string): Route {
  if (pathname === "/" || pathname === "") return { screen: "realtime" };
  // /admin va /admin/... ni normallashtiramiz
  let p = pathname.replace(/^\/admin\/?/, "");
  if (p === "") return { screen: "dashboard" };
  if (p.startsWith("editor/")) {
    return { screen: "editor", id: p.slice("editor/".length) };
  }
  if (p.startsWith("preview")) return { screen: "preview" };
  const screen = p.split("/")[0];
  return { screen };
}

/** Eski `go(route)` callback'ini qaytaradi (router navigate ustida). */
export function useGo(): (route: Route) => void {
  const navigate = useNavigate();
  return (route: Route) => navigate(screenToPath(route));
}
