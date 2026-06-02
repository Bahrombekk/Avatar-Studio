/* Dashboard route — avatarlar ro'yxati. */
import { Dashboard } from "@/components/AdminShell";
import { useAvatars } from "@/context/AvatarsContext";
import { useGo } from "@/app/navigation";

export function DashboardPage() {
  const { avatars } = useAvatars();
  const go = useGo();
  return <Dashboard avatars={avatars} go={go} />;
}
