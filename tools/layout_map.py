"""Instrument the renderer: box map + typographic audit of one frame."""
import sys, math, numpy as np
sys.path.insert(0, 'src')
from cutwright.raster import Raster, col

class Probe(Raster):
    def __init__(s, w, h):
        super().__init__(w, h)
        s.ops = []
    def text(s, txt, x, y, size, family="sans", weight=500, color="#fff", alpha=1.0,
             tracking=0.0, align="left", baseline=True):
        w = s.text_width(txt, size, family, weight, tracking)
        if align == "center": x -= w/2
        elif align == "right": x -= w
        top = y - size*0.78 if baseline else y
        s.ops.append(("text", x, top, w, size*1.0, txt, size, alpha, family, weight))
        return super().text(txt, x if align=="left" else x+w if align=="right" else x+w/2,
                            y, size, family, weight, color, alpha, tracking, align, baseline)
    def rect(s, x, y, w, h, color, alpha=1.0, blur=0.0, blend=None):
        if w>2 and h>2: s.ops.append(("rect", x, y, w, h, "", 0, alpha, "", 0))
        return super().rect(x,y,w,h,color,alpha,blur,blend)
    def rrect(s, x, y, w, h, r, color, alpha=1.0, blur=0.0, blend=None):
        if w>2 and h>2: s.ops.append(("rrect", x, y, w, h, "", 0, alpha, "", 0))
        return super().rrect(x,y,w,h,r,color,alpha,blur,blend)
    def line(s, x1, y1, x2, y2, color, width=1.0, alpha=1.0, blur=0.0):
        s.ops.append(("line", min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1), "", 0, alpha, "", 0))
        return super().line(x1,y1,x2,y2,color,width,alpha,blur)
    def circle(s, cx, cy, r, color, alpha=1.0, blur=0.0, blend=None):
        s.ops.append(("circle", cx-r, cy-r, 2*r, 2*r, "", 0, alpha, "", 0))
        return super().circle(cx,cy,r,color,alpha,blur,blend)

def render_map(film, t, cols=118, rows=36):
    r = Probe(film.W, film.H)
    r.clear("#000000")
    film.draw(r, t)
    grid = [[" "]*cols for _ in range(rows)]
    def put(x,y,w,h,ch):
        c0=max(0,int(x/film.W*cols)); c1=min(cols-1,int((x+w)/film.W*cols))
        r0=max(0,int(y/film.H*rows)); r1=min(rows-1,int((y+h)/film.H*rows))
        for yy in range(r0,r1+1):
            for xx in range(c0,c1+1):
                if grid[yy][xx] not in (" ","T"): grid[yy][xx]="X"
                elif grid[yy][xx]=="T" and ch!="T": grid[yy][xx]="X"
                else: grid[yy][xx]=ch
    for op in r.ops:
        kind,x,y,w,h = op[0],op[1],op[2],op[3],op[4]
        if kind=="text": put(x,y,w,h,"T")
        elif kind=="line": put(x,y,max(w,1),max(h,1),"-")
        else: put(x,y,w,h,"#")
    print(f"=== t={t:.2f}s  ({film._scene_at(t)[0]})")
    for row in grid: print("".join(row))
    print("\n-- typography --")
    m = film.m
    for op in r.ops:
        if op[0]!="text": continue
        _,x,y,w,h,txt,size,a,fam,wt = op
        if a < 0.3 or size < 12: continue
        flag = ""
        if x < m-1 or x+w > film.W-m+1: flag += " OUTSIDE-MARGINS"
        if w > film.W-2*m: flag += " TOO-WIDE"
        print(f"  {txt[:34]!r:38s} x={x:6.1f} y={y:6.1f} w={w:6.1f} size={size:5.1f} {fam}/{wt} a={a:.2f}{flag}")

if __name__ == "__main__":
    from cutwright.comps import LaunchFilm
    from cutwright.theme import Format
    film = LaunchFilm(fmt=Format(1920,1080,30))
    for t in [float(v) for v in sys.argv[1:]] or [3.3]:
        render_map(film, t)
