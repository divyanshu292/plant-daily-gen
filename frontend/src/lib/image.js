// Shrink large photos before upload. The host limits request bodies to 4.5 MB,
// and the reader does not need more than about 2400 px on the long edge.

const MAX_EDGE = 2400;
const MAX_BYTES = 1.5 * 1024 * 1024;
const HARD_LIMIT = 4.3 * 1024 * 1024;

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => resolve({ img, url });
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('decode failed'));
    };
    img.src = url;
  });
}

function toBlob(canvas, quality) {
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality));
}

/**
 * Returns { file, resized, from: {w, h, bytes}, to: {w, h, bytes} }.
 * If the browser cannot decode the image (e.g. HEIC outside Safari) the
 * original file is sent and the server decides.
 */
export async function prepareImage(file) {
  let loaded;
  try {
    loaded = await loadImage(file);
  } catch {
    return { file, resized: false };
  }
  const { img, url } = loaded;
  try {
    // naturalWidth/Height already follow the EXIF orientation in current browsers.
    const w = img.naturalWidth;
    const h = img.naturalHeight;
    const from = { w, h, bytes: file.size };
    const longEdge = Math.max(w, h);
    if (file.size <= MAX_BYTES && longEdge <= MAX_EDGE) return { file, resized: false, from };

    const scale = Math.min(1, MAX_EDGE / longEdge);
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff'; // transparent PNG areas become white, not black
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    let blob = await toBlob(canvas, 0.9);
    if (blob && blob.size > HARD_LIMIT) blob = await toBlob(canvas, 0.75);
    if (!blob) return { file, resized: false, from };

    const out = new File([blob], file.name, { type: 'image/jpeg', lastModified: file.lastModified });
    return { file: out, resized: true, from, to: { w: canvas.width, h: canvas.height, bytes: out.size } };
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function fmtBytes(bytes) {
  if (bytes == null) return '';
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
