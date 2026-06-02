/* "Tez orada" bo'sh holat sahifasi (Suhbatlar, Foydalanuvchilar). */
import { I } from "@/lib/icons";
import { Topbar } from "@/components/AdminShell";
import { Badge } from "@/components/ui";

interface PlaceholderProps {
  icon: string;
  title: string;
  desc: string;
}

export function Placeholder({ icon, title, desc }: PlaceholderProps) {
  const Ico = I[icon];
  return (
    <div className="pg">
      <Topbar title={title} />
      <div className="ph">
        <div className="ph-ico">
          <Ico size={30} />
        </div>
        <div className="ph-t">{title}</div>
        <div className="ph-d">{desc}</div>
        <Badge color="var(--ink-3)">Tez orada</Badge>
      </div>
    </div>
  );
}
