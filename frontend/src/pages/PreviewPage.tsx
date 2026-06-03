/* Jonli ko'rinish route — admin chrome'siz to'liq ekran chat. */
import { useNavigate, useParams } from "react-router-dom";
import { I } from "@/lib/icons";
import { ChatScreen } from "@/pages/ChatScreen";
import { StudioTweaks } from "@/app/StudioTweaks";
import { useAvatars } from "@/context/AvatarsContext";
import { useTweaksCtx, applyTweaksToAvatar } from "@/context/TweaksContext";

export function PreviewPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const { avatars } = useAvatars();
  const { t } = useTweaksCtx();
  // Avval URL'dagi avatar (tahrirdan "Ko'rish" bosilganda), keyin live, keyin birinchi.
  const previewAvatar =
    (id && avatars.find((a) => a.id === id)) ||
    avatars.find((a) => a.status === "live") ||
    avatars[0];

  return (
    <>
      <div className="pv-wrap">
        <button className="pv-back" onClick={() => navigate("/admin")}>
          <I.back size={15} /> Panelga qaytish
        </button>
        <div className="pv-stage">
          {previewAvatar ? (
            <ChatScreen
              avatar={applyTweaksToAvatar(previewAvatar, t)}
              embedded
            />
          ) : (
            <div className="pv-empty">Avatarlar yuklanmoqda…</div>
          )}
        </div>
      </div>
      <StudioTweaks />
    </>
  );
}
