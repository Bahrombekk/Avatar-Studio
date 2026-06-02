/* Analitika route. */
import { Analytics } from "@/pages/Analytics";
import { useAvatars } from "@/context/AvatarsContext";

export function AnalyticsPage() {
  const { avatars } = useAvatars();
  return <Analytics avatars={avatars} />;
}
