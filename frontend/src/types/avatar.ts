/* Avatar va build (fon job) tiplari. */

export type AvatarStatus = "draft" | "processing" | "live" | string;

/**
 * Avatar yozuvi — backend JSON'idan keladi. UI ko'plab ixtiyoriy maydonlarni
 * o'qiydi/yozadi, shuning uchun ma'lum maydonlar + permissiv index imzosi.
 */
export interface Avatar {
  id: string;
  name: string;
  role?: string;
  status?: AvatarStatus;
  voice?: string;
  lang?: string;
  language?: string;
  real?: boolean;
  hasArtifact?: boolean;
  hasMotion?: boolean;
  hasPhoto?: boolean;
  extraMargin?: number;
  updated?: string;
  [key: string]: unknown;
}

/** Yangi avatar yaratish yoki tahrirlash uchun qisman ma'lumot. */
export type AvatarDraft = Partial<Avatar> & { name: string };

export type BuildState = "idle" | "processing" | "done" | "error" | string;
export type BuildStage = "idle_gen" | "musetalk_prep" | string;

/** GET /api/avatars/{id}/build javobi (polling). */
export interface BuildStatus {
  state: BuildState;
  stage?: BuildStage;
  error?: string;
  [key: string]: unknown;
}
