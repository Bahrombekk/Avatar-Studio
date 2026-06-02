/* Avatarlar ro'yxati — global kontekst (barcha route'lar bo'lishadi).
   Backend bilan sinxron: reload / saveAvatar / deleteAvatar. */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { API } from "@/api/client";
import { useToast } from "@/context/ToastContext";
import type { Avatar, AvatarDraft } from "@/types/avatar";

interface AvatarsContextValue {
  avatars: Avatar[];
  reload: () => Promise<void>;
  saveAvatar: (draft: AvatarDraft) => Promise<void>;
  deleteAvatar: (id: string) => Promise<void>;
}

const AvatarsContext = createContext<AvatarsContextValue | null>(null);

export function AvatarsProvider({ children }: { children: ReactNode }) {
  const [avatars, setAvatars] = useState<Avatar[]>([]);
  const { toast } = useToast();

  const reload = useCallback(async () => {
    try {
      setAvatars(await API.listAvatars());
    } catch (e) {
      console.error(e);
      toast("Avatarlar yuklanmadi", "error");
    }
  }, [toast]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const saveAvatar = useCallback(
    async (draft: AvatarDraft) => {
      try {
        const isNew = !draft.id || draft.id === "new";
        if (isNew) {
          const { id: _id, ...payload } = draft;
          void _id;
          await API.createAvatar(payload as AvatarDraft);
        } else {
          await API.updateAvatar(draft.id as string, draft);
        }
        await reload();
        toast("Saqlandi", "success");
      } catch (e) {
        console.error(e);
        toast("Saqlashda xatolik: " + (e as Error).message, "error");
      }
    },
    [reload, toast],
  );

  const deleteAvatar = useCallback(
    async (id: string) => {
      try {
        await API.deleteAvatar(id);
        await reload();
        toast("O'chirildi", "success");
      } catch (e) {
        console.error(e);
        toast("O'chirishda xatolik: " + (e as Error).message, "error");
      }
    },
    [reload, toast],
  );

  return (
    <AvatarsContext.Provider
      value={{ avatars, reload, saveAvatar, deleteAvatar }}
    >
      {children}
    </AvatarsContext.Provider>
  );
}

export function useAvatars(): AvatarsContextValue {
  const ctx = useContext(AvatarsContext);
  if (!ctx) {
    throw new Error("useAvatars AvatarsProvider ichida ishlatilishi kerak");
  }
  return ctx;
}
