"""Extract frames at given times into one labelled contact sheet PNG."""
import subprocess, sys, cv2, numpy as np
from pathlib import Path
F = str(Path.home()/'.local/bin/ffmpeg')

def grab(video, t, w=480):
    out = subprocess.run([F,'-hide_banner','-loglevel','error','-ss',str(t),'-i',video,
                          '-frames:v','1','-vf',f'scale={w}:-2','-f','image2pipe','-vcodec','png','-'],
                         capture_output=True)
    arr = np.frombuffer(out.stdout, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def sheet(video, times, out, cols=3, w=480):
    imgs = [grab(video, t, w) for t in times]
    imgs = [im for im in imgs if im is not None]
    h, ww = imgs[0].shape[:2]
    rows = (len(imgs)+cols-1)//cols
    canvas = np.zeros((rows*h, cols*ww, 3), np.uint8)
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        canvas[r*h:(r+1)*h, c*ww:(c+1)*ww] = im
        cv2.putText(canvas, f"{times[i]:.1f}s", (c*ww+14, r*h+28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 1, cv2.LINE_AA)
    cv2.imwrite(out, canvas)
    print(out, canvas.shape)

if __name__ == '__main__':
    vid = sys.argv[1]; outp = sys.argv[2]
    times = [float(x) for x in sys.argv[3].split(',')]
    sheet(vid, times, outp)
