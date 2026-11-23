import io
import os
import zipfile
import numpy as np
from PIL import Image

ZIP_PATH = '/Users/xzm/.gemini/antigravity/brain/2b548173-5df1-4930-b51b-d40db9e87399/.user_uploaded/media_1795415399405_ec007adb.zip'
OUT_DIR = '/Users/xzm/Downloads/antShip/textures'
os.makedirs(OUT_DIR, exist_ok=True)


def make_emissive(arr_rgb):
    f = arr_rgb.astype(np.float32)
    R, G, B = f[:, :, 0], f[:, :, 1], f[:, :, 2]
    score = (
        np.clip((B - 150.0) / 55.0, 0.0, 1.0)
        * np.clip((G - 140.0) / 55.0, 0.0, 1.0)
        * np.clip(((B - R) - 40.0) / 45.0, 0.0, 1.0)
    )
    out = np.zeros_like(f)
    out[:, :, 0] = np.clip(score * 0.12 * 255.0, 0, 255)
    out[:, :, 1] = np.clip(score * 0.90 * 255.0, 0, 255)
    out[:, :, 2] = np.clip(score * 1.00 * 255.0, 0, 255)
    return Image.fromarray(out.astype(np.uint8))


with zipfile.ZipFile(ZIP_PATH) as z:
    im = Image.open(io.BytesIO(z.read('06-rear.png'))).convert('RGB')

crops = [
    ('nozzle_face_center.png', 'nozzle_emit_center.png', (531, 423, 723, 615)),
    ('nozzle_face_side.png',   'nozzle_emit_side.png',   (325, 436, 493, 604)),
]

for face_name, emit_name, box in crops:
    sub = im.crop(box).resize((512, 512), Image.LANCZOS)
    sub.save(os.path.join(OUT_DIR, face_name))
    em = make_emissive(np.array(sub))
    em.save(os.path.join(OUT_DIR, emit_name))
    print("Saved:", face_name, emit_name)
