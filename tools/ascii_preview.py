"""Render a frame as a readable luminance map (no image input needed)."""
import sys, numpy as np, cv2
RAMP = " .:-=+*#%@"
def preview(path, w=110, gamma=0.65):
    img = cv2.imread(path)
    h = max(1, int(w * img.shape[0] / img.shape[1] * 0.45))
    small = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
    lum = (0.0722*small[...,0] + 0.7152*small[...,1] + 0.2126*small[...,2]) / 255.0
    lum = lum ** gamma
    print(f"--- {path}  mean_lum={lum.mean():.3f} max={lum.max():.3f}")
    for row in lum:
        print("".join(RAMP[min(9, int(v*9.999))] for v in row))
if __name__ == "__main__":
    for p in sys.argv[1:]:
        preview(p)
