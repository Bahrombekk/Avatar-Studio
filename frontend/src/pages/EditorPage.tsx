/* Avatar muharriri route — /editor/new yoki /editor/:id. */
import { useNavigate, useParams } from "react-router-dom";
import { AvatarEditor } from "@/pages/AvatarEditor";
import { useAvatars } from "@/context/AvatarsContext";
import { useGo } from "@/app/navigation";
import type { AvatarDraft } from "@/types/avatar";

export function EditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const go = useGo();
  const { avatars, saveAvatar, deleteAvatar } = useAvatars();

  const found = avatars.find((a) => a.id === id);
  // Ro'yxat hali yuklanmagan bo'lsa, mavjud avatarni "yangi" deb adashtirmaymiz.
  if (id !== "new" && !found && avatars.length === 0) return null;
  const editing = id === "new" ? null : (found ?? null);

  return (
    <AvatarEditor
      base={editing}
      onSave={async (draft: AvatarDraft) => {
        await saveAvatar(draft);
        navigate("/");
      }}
      onDelete={async (avId: string) => {
        await deleteAvatar(avId);
        navigate("/");
      }}
      onCancel={() => navigate("/")}
      go={go}
    />
  );
}
