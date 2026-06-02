/* Eski {screen,id} navigatsiya API'si ↔ react-router URL ko'prigi.
   .jsx komponentlar hali `go({screen,id})` va `route.screen` ishlatadi —
   ularni o'zgartirmasdan router bilan ishlashga imkon beradi (Faza 4'da TS'ga ko'chadi). */
import { useNavigate } from "react-router-dom";

export interface Route {
  screen: string;
  id?: string;
}

/** {screen,id} → URL yo'li. */
export function screenToPath(route: Route): string {
  switch (route.screen) {
    case "dashboard":
      return "/";
    case "editor":
      return "/editor/" + (route.id || "new");
    case "analytics":
      return "/analytics";
    case "conversations":
      return "/conversations";
    case "users":
      return "/users";
    case "settings":
      return "/settings";
    case "preview":
      return route.id ? "/preview/" + route.id : "/preview";
    default:
      return "/";
  }
}

/** URL yo'li → {screen,id} (Sidebar'ning active holati uchun). */
export function pathToRoute(pathname: string): Route {
  if (pathname === "/" || pathname === "") return { screen: "dashboard" };
  if (pathname.startsWith("/editor/")) {
    return { screen: "editor", id: pathname.slice("/editor/".length) };
  }
  const screen = pathname.replace(/^\//, "").split("/")[0];
  return { screen };
}

/** Eski `go(route)` callback'ini qaytaradi (router navigate ustida). */
export function useGo(): (route: Route) => void {
  const navigate = useNavigate();
  return (route: Route) => navigate(screenToPath(route));
}
