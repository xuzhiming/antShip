import io
import os
import zipfile
import numpy as np
from PIL import Image, ImageFilter

ZIP_PATH = '/Users/xzm/.gemini/antigravity/brain/2b548173-5df1-4930-b51b-d40db9e87399/.user_uploaded/media_1795415399405_ec007adb.zip'
OUT_DIR = '/Users/xzm/Downloads/antShip/textures'
os.makedirs(OUT_DIR, exist_ok=True)


def inpaint_dilate_rgb(rgb, seed_mask):
    """Fill all non-seed pixels using Jump Flooding Algorithm (nearest foreground RGB)."""
    h, w, _ = rgb.shape
    INF = 1e12
    sy = np.full((h, w), -1, dtype=np.int32)
    sx = np.full((h, w), -1, dtype=np.int32)
    dist2 = np.full((h, w), INF, dtype=np.float32)

    ys, xs = np.where(seed_mask)
    sy[ys, xs] = ys
    sx[ys, xs] = xs
    dist2[ys, xs] = 0.0

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    step = 1
    while step < max(h, w):
        step *= 2
    step //= 2

    while step >= 1:
        for dy in (-step, 0, step):
            for dx in (-step, 0, step):
                if dy == 0 and dx == 0:
                    continue
                y0_dst = max(0, -dy); y1_dst = min(h, h - dy)
                x0_dst = max(0, -dx); x1_dst = min(w, w - dx)
                if y1_dst <= y0_dst or x1_dst <= x0_dst:
                    continue
                y0_src = y0_dst + dy; y1_src = y1_dst + dy
                x0_src = x0_dst + dx; x1_src = x1_dst + dx

                cand_y = sy[y0_src:y1_src, x0_src:x1_src]
                cand_x = sx[y0_src:y1_src, x0_src:x1_src]
                valid = cand_y >= 0
                d2_new = np.where(
                    valid,
                    (yy[y0_dst:y1_dst, x0_dst:x1_dst] - cand_y) ** 2
                    + (xx[y0_dst:y1_dst, x0_dst:x1_dst] - cand_x) ** 2,
                    INF,
                )
                cur_d2 = dist2[y0_dst:y1_dst, x0_dst:x1_dst]
                better = d2_new < cur_d2
                if np.any(better):
                    cur_d2[better] = d2_new[better]
                    sy[y0_dst:y1_dst, x0_dst:x1_dst][better] = cand_y[better]
                    sx[y0_dst:y1_dst, x0_dst:x1_dst][better] = cand_x[better]
        step //= 2

    return rgb[sy, sx]


def prep_view(rgba, out_w, out_h, x_knots_src, x_knots_dst, y_knots_src, y_knots_dst):
    alpha = rgba[:, :, 3]
    fg = alpha > 200
    # Erode by 1 px to discard semi-transparent anti-aliased fringe
    seed = fg.copy()
    seed[1:-1, 1:-1] &= fg[:-2, 1:-1] & fg[2:, 1:-1] & fg[1:-1, :-2] & fg[1:-1, 2:]
    seed[0, :] = False; seed[-1, :] = False; seed[:, 0] = False; seed[:, -1] = False

    filled = inpaint_dilate_rgb(rgba[:, :, :3], seed).astype(np.float32)
    sh, sw, _ = filled.shape

    u_dst = np.linspace(0, out_w - 1, out_w, dtype=np.float32)
    v_dst = np.linspace(0, out_h - 1, out_h, dtype=np.float32)
    x_map = np.clip(np.interp(u_dst, x_knots_dst, x_knots_src), 0, sw - 1.001)
    y_map = np.clip(np.interp(v_dst, y_knots_dst, y_knots_src), 0, sh - 1.001)

    x0 = np.floor(x_map).astype(np.int32)
    y0 = np.floor(y_map).astype(np.int32)
    wx = (x_map - x0)[None, :, None]
    wy = (y_map - y0)[:, None, None]

    c00 = filled[y0[:, None], x0[None, :]]
    c10 = filled[y0[:, None], x0[None, :] + 1]
    c01 = filled[y0[:, None] + 1, x0[None, :]]
    c11 = filled[y0[:, None] + 1, x0[None, :] + 1]

    warped = (
        c00 * (1 - wx) * (1 - wy)
        + c10 * wx * (1 - wy)
        + c01 * (1 - wx) * wy
        + c11 * wx * wy
    )
    out_im = Image.fromarray(np.clip(warped, 0, 255).astype(np.uint8))
    return out_im


with zipfile.ZipFile(ZIP_PATH) as z:
    def load_zip_rgba(fname):
        return np.array(Image.open(io.BytesIO(z.read(fname))).convert('RGBA'))

    # Z=0 row in a 1024-tall canvas spanning Z[-22.5 .. +23.0]:
    # Z=0 is at v = 22.5/45.5 = 0.494505 -> row = 1023 * (1 - 0.494505) = 517.12
    Z0_ROW = 517.12

    # 1. 01-left.png (2172x724) - uniform linear X
    left_arr = load_zip_rgba('01-left.png')
    hd_left = prep_view(
        left_arr, 2048, 1024,
        [197.0, 2056.0],      [0.0, 2047.0],
        [21.0, 369.0, 718.0], [0.0, Z0_ROW, 1023.0],
    )
    hd_left.save(os.path.join(OUT_DIR, 'hd_left.png'))

    # 2. 02-right.png (2179x721) - flip horizontally, uniform linear X
    right_arr = load_zip_rgba('02-right.png')[:, ::-1, :]
    ra = right_arr[:, :, 3] > 128
    r_xs = np.where(ra)[1]
    print(f"02-right flipped uniform X: [{r_xs.min()}, {r_xs.max()}]")
    hd_right = prep_view(
        right_arr, 2048, 1024,
        [float(r_xs.min()), float(r_xs.max())], [0.0, 2047.0],
        [13.0, 368.0, 713.0], [0.0, Z0_ROW, 1023.0],
    )
    hd_right.save(os.path.join(OUT_DIR, 'hd_right.png'))

    # 3. 03-top.png (2172x724)
    top_arr = load_zip_rgba('03-top.png')
    hd_top = prep_view(
        top_arr, 2048, 1024,
        [70.0, 2102.0],       [0.0, 2047.0],
        [57.0, 370.0, 682.0], [0.0, 511.5, 1023.0],
    )
    hd_top.save(os.path.join(OUT_DIR, 'hd_top.png'))

    # 4. 04-bottom.png (2172x724)
    bot_arr = load_zip_rgba('04-bottom.png')
    hd_bottom = prep_view(
        bot_arr, 2048, 1024,
        [46.0, 2142.0],       [0.0, 2047.0],
        [40.0, 372.0, 693.0], [0.0, 511.5, 1023.0],
    )
    hd_bottom.save(os.path.join(OUT_DIR, 'hd_bottom.png'))

    # 5. 05-front.png (1254x1254)
    front_arr = load_zip_rgba('05-front.png')
    hd_front = prep_view(
        front_arr, 1024, 1024,
        [8.0, 627.0, 1244.0], [0.0, 511.5, 1023.0],
        [6.0, 526.0, 1243.0], [0.0, Z0_ROW, 1023.0],
    )
    hd_front.save(os.path.join(OUT_DIR, 'hd_front.png'))

    # 6. 06-rear.png (1254x1254)
    rear_arr = load_zip_rgba('06-rear.png')
    hd_rear = prep_view(
        rear_arr, 1024, 1024,
        [23.0, 627.0, 1230.0], [0.0, 511.5, 1023.0],
        [11.0, 526.0, 1241.0], [0.0, Z0_ROW, 1023.0],
    )
    hd_rear.save(os.path.join(OUT_DIR, 'hd_rear.png'))

print("All 6 HD projection views saved to", OUT_DIR)
