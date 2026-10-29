"""Post-process snk SVGs: drop the progress bar, then play Conway's Game of Life
on the contribution grid once the snake is done. Usage: python3 gol.py dist/*.svg"""
import random, re, sys, datetime

GENS = 40          # generations to play
STEP = 200         # ms per generation
HOLD = 1500        # ms to hold the last generation before the loop restarts
DENSITY = 0.3      # top up the seed with random cells up to this density

def process(path):
    svg = open(path).read()

    # 1. remove the progress bar and crop it out of the viewBox
    svg = re.sub(r'<rect class="u[^"]*"[^>]*/>', '', svg)
    vx, vy, vw, vh = map(float, re.search(r'viewBox="([^"]+)"', svg).group(1).split())
    bottom = max(int(y) for y in re.findall(r'<rect class="c[^"]*" x="\d+" y="(\d+)"', svg)) + 12 + 16
    vh = bottom - vy
    svg = re.sub(r'viewBox="[^"]+" width="(\d+)" height="\d+"',
                 lambda m: f'viewBox="{vx:g} {vy:g} {vw:g} {vh:g}" width="{m.group(1)}" height="{vh:g}"', svg, count=1)

    # 2. stretch the snake timeline so there is room for the game of life afterwards
    t = int(re.search(r'(\d+)ms', svg).group(1))
    total = t + GENS * STEP + HOLD
    k = t / total
    svg = svg.replace(f'{t}ms', f'{total}ms')

    def rescale(m):
        stops = re.findall(r'([\d.%,]+)\{([^}]*)\}', m.group(2))
        out, top, top_i = [], -1, 0
        for i, (sel, body) in enumerate(stops):
            pcts = [float(p) * k for p in sel.rstrip('%').split('%,')]
            if max(pcts) > top:
                top, top_i = max(pcts), i
            out.append([','.join(f'{p:.3f}'.rstrip('0').rstrip('.') + '%' for p in pcts), body])
        out[top_i][0] += ',100%'  # hold the snake's final state until the loop restarts
        return '@keyframes ' + m.group(1) + '{' + ''.join(f'{s}{{{b}}}' for s, b in out) + '}'
    svg = re.sub(r'@keyframes (\w+)\{((?:[\d.%,]+\{[^}]*\})+)\}', rescale, svg)

    # 3. game of life, seeded from the contribution grid
    level = {cls: int(n) for cls, n in re.findall(r'\.c\.(\w+)\{fill:var\(--c(\d)\)', svg)}
    cells = {}
    for cls, x, y in re.findall(r'<rect class="c(?: (\w+))?" x="(\d+)" y="(\d+)"', svg):
        cells[((int(x) - 2) // 16, (int(y) - 2) // 16)] = (x, y, level.get(cls, 0) > 0)
    w = max(c for c, _ in cells) + 1
    h = max(r for _, r in cells) + 1

    rng = random.Random(datetime.date.today().isoformat())
    alive = {p for p, (_, _, on) in cells.items() if on}
    empty = [p for p in cells if p not in alive]
    rng.shuffle(empty)
    alive |= set(empty[:max(0, int(DENSITY * len(cells)) - len(alive))])

    age = {p: 1 for p in alive}
    history = [dict(age)]
    for _ in range(GENS - 1):
        nxt = {}
        for p in cells:
            n = sum(((p[0] + dx) % w, (p[1] + dy) % h) in age
                    for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)
            if n == 3 or (n == 2 and p in age):
                nxt[p] = age.get(p, 0) + 1
        age = nxt
        history.append(dict(age))

    def color(a):  # newborn = brightest, fades with age
        return f'var(--c{max(1, 5 - a)})' if a else 'transparent'

    pct = lambda ms: f'{ms / total * 100:.3f}'.rstrip('0').rstrip('.') + '%'
    css, rects, frames = [f'.g{{width:12px;height:12px;fill:transparent;animation:none {total}ms step-end infinite}}'], [], {}
    for p, (x, y, _) in cells.items():
        stops, prev = ['0%{fill:transparent}'], 'transparent'
        for i, gen in enumerate(history):
            c = color(gen.get(p, 0))
            if c != prev:
                stops.append(f'{pct(t + i * STEP)}{{fill:{c}}}')
                prev = c
        if len(stops) == 1:
            continue
        stops.append('100%{fill:transparent}')
        body = ''.join(stops)
        if body not in frames:
            frames[body] = f'g{len(frames):x}'
            css.append(f'@keyframes {frames[body]}{{{body}}}.g.{frames[body]}{{animation-name:{frames[body]}}}')
        rects.append(f'<rect class="g {frames[body]}" x="{x}" y="{y}" rx="2" ry="2"/>')

    svg = svg.replace('</style>', ''.join(css) + '</style>', 1)
    first_snake = svg.index('<rect class="s')
    svg = svg[:first_snake] + ''.join(rects) + svg[first_snake:]
    open(path, 'w').write(svg)

for f in sys.argv[1:]:
    process(f)
