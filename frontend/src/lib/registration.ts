export const EMAIL_PROOF_KEY = "airate.registration"
export type EmailProof = {email: string; ticket: string; expiresAt: number; resendAt: number}

export function restoreEmailProof(raw: string | null, now = Date.now()): EmailProof | null {
  try {
    const value = JSON.parse(raw || "null")
    return value && typeof value.email === "string" && typeof value.ticket === "string"
      && /^[A-Za-z0-9_-]{30,200}$/.test(value.ticket) && Number.isFinite(value.expiresAt)
      && value.expiresAt > now && Number.isFinite(value.resendAt) ? value : null
  } catch { return null }
}
