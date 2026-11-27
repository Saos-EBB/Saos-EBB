"""Fixed shooter on the contribution grid: a little dart-shaped ship sweeps along the
bottom and shoots the cells out column by column, lowest first; each hit fades a cell
by one level, the last one pops it (flash, gone). The grid creeps down as it thins out.
Precomputed here, emitted as pure CSS keyframes (no JS, works inside an <img>).
Usage: python games/invaders.py OUT_LIGHT.svg OUT_DARK.svg"""
import sys
import grid as G

SHIP_Y = 124            # ship nose; the ship occupies y 124..137, its exhaust y 137..140
MUZZLE = 126            # bullets leave the ship's nose here (bottom edge of the 6-unit bullet)
BULLET_V = 0.6          # svg units per ms
SHIP_V = 0.45           # svg units per ms when moving between columns
PLAY = 20000            # aimed length of the shooting phase, ms
SHOT_MIN, SHOT_MAX = 45, 140   # ms between shots (picked so the play phase is ~PLAY)
FLASH = 80              # ms a hit cell flashes in the ship colour
POP = 140               # ms the final hit flashes before the cell is gone
DROPS, DROP = 3, 2      # the grid steps down DROPS times by DROP units while it is shot at
HOLD = 1000             # ms the empty grid is held
REBUILD = 1600          # ms the ship glides back and the grid reappears in its wake
POOL = 8                # bullet elements, reused round robin


def col_x(w):
    return 16 * w + 8


def build(grid):
    lvl = {(w, d): v for w, col in enumerate(grid) for d, v in enumerate(col) if v}
    fills = {p: [(0, f'var(--c{v})')] for p, v in lvl.items()}
    shots_needed = sum(lvl.values())
    cols = sorted({w for w, _ in lvl})
    x0, x1 = col_x(0), col_x(G.WEEKS - 1)
    travel = (x1 - x0) / SHIP_V
    shot = max(SHOT_MIN, min(SHOT_MAX, (PLAY - travel) / max(1, shots_needed)))
    play_est = travel + shot * shots_needed
    drop_every = play_est / (DROPS + 1)
    shift = lambda t: DROP * min(DROPS, int(t // drop_every))

    ship = [(0, x0)]                     # (ms, x)
    shots = []                           # (fire ms, impact ms, x, impact y)
    t, x = 600.0, x0                     # short pause before the first move
    ship.append((t, x))
    for w in cols:
        tx = col_x(w)
        t += abs(tx - x) / SHIP_V
        x = tx
        ship.append((t, x))
        for d in range(G.DAYS - 1, -1, -1):  # lowest cell first
            while lvl.get((w, d)):
                cy = 16 * d + 2 + 12        # bottom edge of the cell, before the drop
                imp = t
                for _ in range(3):         # the grid may drop while the bullet flies
                    imp = t + max(0, MUZZLE - 6 - (cy + shift(imp))) / BULLET_V
                yb = cy + shift(imp) + 6   # bullet bottom when its top touches the cell
                shots.append((t, imp, x, yb))
                lvl[w, d] -= 1
                if lvl[w, d]:
                    fills[w, d] += [(imp, 'var(--cs)'), (imp + FLASH, f'var(--c{lvl[w, d]})')]
                else:
                    fills[w, d] += [(imp, 'var(--cs)'), (imp + POP, 'var(--ce)')]
                    del lvl[w, d]
                t += shot
        ship.append((t, x))
    # finish the sweep to the right edge
    t += (x1 - x) / SHIP_V
    ship.append((t, x1))
    end = max(t, max((s[1] for s in shots), default=t) + POP)
    total = round(end + HOLD + REBUILD)
    clock = G.Clock(total)
    eps = total / 100000 * 1.01        # one keyframe quantum

    # rebuild: the ship flies back right to left, cells reappear as it passes under them
    back = end + HOLD
    ship += [(back, x1), (total, x0)]
    for (w, d), stops in fills.items():
        at = back + (x1 - col_x(w)) / (x1 - x0) * REBUILD
        stops += [(at, 'var(--cs)'), (min(total - eps, at + 120), f'var(--c{grid[w][d]})')]

    cell_css, cell_svg = G.cells_svg(grid, clock, fills)

    # grid drops (step-end), snaps back when the rebuild starts
    gstops = [(0, 'transform:translateY(0px)')]
    for k in range(1, DROPS + 1):
        if k * drop_every < end:
            gstops.append((k * drop_every, f'transform:translateY({DROP * k}px)'))
    gstops.append((back, 'transform:translateY(0px)'))

    # bullets
    pool = [[] for _ in range(POOL)]
    for i, (f, imp, bx, by) in enumerate(shots):
        lane = pool[i % POOL]
        if lane:
            assert lane[-1][0] + eps < f - eps, 'bullet pool too small'
        lane += [(f - eps, bx, MUZZLE, 0), (f, bx, MUZZLE, 1), (imp, bx, by, 1), (imp + eps, bx, by, 0)]
    css = [cell_css,
           f'.gr{{animation:gr {total}ms step-end infinite}}@keyframes gr{{{G.frames(clock, gstops)}}}',
           f'.sh,.bl,.fl{{fill:var(--cs)}}.sh{{animation:sh {total}ms linear infinite}}',
           f'@keyframes sh{{{G.frames(clock, [(ms, f"transform:translateX({sx:.1f}px)") for ms, sx in ship])}}}',
           f'.fl{{animation:fl 180ms steps(2,jump-none) infinite}}@keyframes fl{{0%{{opacity:.9}}100%{{opacity:.25}}}}',
           f'.bl{{opacity:0;animation:none {total}ms linear infinite}}']
    bullets = []
    for k, lane in enumerate(pool):
        if not lane:
            continue
        first, last = lane[0], lane[-1]
        stops = [(0, first[1], first[2], 0)] + lane + [(total, last[1], last[2], 0)]
        body = G.frames(clock, [(ms, f'transform:translate({bx:.1f}px,{by:.1f}px);opacity:{o}')
                                for ms, bx, by, o in stops])
        css.append(f'@keyframes b{k}{{{body}}}.bl.b{k}{{animation-name:b{k}}}')
        bullets.append(f'<rect class="bl b{k}" x="-1" y="-6" width="2" height="6" rx="1" ry="1"/>')
    # ship: a dart with swept-back wings and a notched tail, nose at SHIP_Y, drawn around x=0
    y = SHIP_Y
    ship_svg = (f'<g class="sh"><path d="M0 {y}L3 {y + 7}L9 {y + 13}L3 {y + 11}'
                f'L0 {y + 13}L-3 {y + 11}L-9 {y + 13}L-3 {y + 7}Z"/>'
                f'<rect class="fl" x="-1.5" y="{y + 13}" width="3" height="3" rx="1" ry="1"/></g>')
    body = f'<g class="gr">{cell_svg}</g>{"".join(bullets)}{ship_svg}'
    stats = dict(total=total, play=round(end), shots=len(shots), shot_ms=round(shot))
    return ''.join(css), body, stats


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    css, body, stats = build(G.load_grid())
    G.write_svgs(sys.argv[1], sys.argv[2], css, body, 'contribution shooter')
    print('invaders:', stats, file=sys.stderr)


if __name__ == '__main__':
    main()
