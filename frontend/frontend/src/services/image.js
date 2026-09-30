const MAX_SIDE = 1568; // longest edge sent to the model; larger images only add latency
const PASS_THROUGH_BYTES = 1_500_000;

function readAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(new Error('The file could not be read.'));
    r.readAsDataURL(file);
  });
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('This file is not a readable image.'));
    img.src = url;
  });
}

/**
 * Validates and (if needed) downsizes the image in the browser so the upload is small and the
 * model call is fast. Returns everything needed to keep the image for retries.
 */
export async function prepareImage(file) {
  if (!file) throw new Error('No file selected.');
  if (!/^image\/(png|jpe?g|webp)$/i.test(file.type)) {
    throw new Error('Please choose a PNG or JPG/JPEG image.');
  }
  if (file.size > 25 * 1024 * 1024) throw new Error('The image is larger than 25 MB.');
  const original = await readAsDataURL(file);
  const img = await loadImage(original);
  const longest = Math.max(img.width, img.height);
  if (img.width < 200 || img.height < 200) {
    throw new Error('The image is too small to read (minimum 200 x 200 pixels).');
  }
  if (file.size <= PASS_THROUGH_BYTES && longest <= MAX_SIDE) {
    return { name: file.name, dataUrl: original, base64: original.split(',')[1], mime: file.type, bytes: file.size, width: img.width, height: img.height, resized: false };
  }
  const scale = Math.min(1, MAX_SIDE / longest);
  const w = Math.round(img.width * scale);
  const h = Math.round(img.height * scale);
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, w, h);
  ctx.drawImage(img, 0, 0, w, h);
  let quality = 0.9;
  let dataUrl = canvas.toDataURL('image/jpeg', quality);
  while (dataUrl.length * 0.75 > 3_400_000 && quality > 0.4) {
    quality -= 0.1;
    dataUrl = canvas.toDataURL('image/jpeg', quality);
  }
  return { name: file.name, dataUrl, base64: dataUrl.split(',')[1], mime: 'image/jpeg', bytes: Math.round(dataUrl.length * 0.75), width: w, height: h, resized: true };
}
