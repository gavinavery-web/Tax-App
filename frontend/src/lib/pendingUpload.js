// Pending upload helper — stash a failed upload in sessionStorage so we can
// retry it after the user completes the Drive OAuth round-trip.
const KEY = "pendingUpload";

const fileToB64 = (file) =>
  new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });

const b64ToFile = (b64, name, type) => {
  const [, payload] = b64.split(",");
  const bin = atob(payload);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new File([bytes], name, { type });
};

export const stashPendingUpload = async (file, meta) => {
  // Skip if file is too big for sessionStorage (~5MB practical cap)
  if (file.size > 4 * 1024 * 1024) return false;
  const b64 = await fileToB64(file);
  sessionStorage.setItem(
    KEY,
    JSON.stringify({ b64, filename: file.name, type: file.type, meta }),
  );
  return true;
};

export const popPendingUpload = () => {
  const raw = sessionStorage.getItem(KEY);
  if (!raw) return null;
  sessionStorage.removeItem(KEY);
  try {
    const data = JSON.parse(raw);
    return { file: b64ToFile(data.b64, data.filename, data.type), meta: data.meta };
  } catch {
    return null;
  }
};

export const hasPendingUpload = () => !!sessionStorage.getItem(KEY);
