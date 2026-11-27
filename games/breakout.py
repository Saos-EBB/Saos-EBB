"""Brick breaker on the contribution grid: the cells are the bricks, every hit fades a
brick by one level and a brick's last level is smashed straight through (the ball keeps
going), which keeps rallies short enough to clear a real calendar in ~20 s. Simulated
deterministically here, emitted as pure CSS keyframes (no JS, works inside an <img>).
Usage: python games/breakout.py OUT_LIGHT.svg OUT_DARK.svg"""
import math, random, sys
import grid as G

SPEED = 0.8            # ball speed, svg units per ms
R = 3                  # ball radius
XMIN, XMAX = -16 + R, 864 - R   # ball centre bounces off the viewBox sides
YMIN = -8              # ball centre bounces off this ceiling (just above the grid)
PW, PH, PY = 48, 6, 124          # paddle width/height, paddle top edge
BALL_Y = PY - R        # ball centre when it touches the paddle
MAX_SIN = 0.94         # max |vx|/speed off the paddle (keeps the ball from going flat)
FLASH = 90             # ms a hit brick flashes in the ball colour
LAUNCH = 500           # ms the ball rests on the paddle before the serve
PLAY_MAX = 23000       # stop serving after this, even if bricks remain
HOLD = 1200            # ms the cleared grid is held
REBUILD = 1500         # ms to rebuild the grid column by column (and reset ball + paddle)
REACH = 48             # svg units: how strongly the aim prefers nearby columns
# A hit fades a brick by one level. If the brick is then below `pierce` the ball smashes
# straight through it instead of bouncing; pierce=1 means the last level of every brick.
# build() raises pierce (and tries a few seeds) until the grid gets cleared in time.
PIERCES, SEEDS = (1, 2, 3, 4, 5), 4
STEP = 0.5             # simulation substep, svg units


def simulate(grid, seed, pierce=1):
    rng = random.Random(seed)
    lvl = {(w, d): v for w, col in enumerate(grid) for d, v in enumerate(col) if v}
    fills = {p: [(0, f'var(--c{v})')] for p, v in lvl.items()}
    ball, paddle = [], []          # (ms, x, y) / (ms, centre x)

    def aim(x):
        """Pick a direction towards a random brick; returns (vx, vy, landing offset on the paddle)."""
        alive = list(lvl)
        if not alive:
            return 0, -SPEED, 0
        # weighted towards bricks near the ball: short rallies, many hits per second
        w, d = rng.choices(alive, [1 / (1 + abs(16 * c + 8 - x) / REACH) ** 2 for c, _ in alive])[0]
        tx, ty = 16 * w + 8, 16 * d + 8
        dx, dy = tx - x, ty - BALL_Y
        n = math.hypot(dx, dy)
        s = dx / n
        if abs(s) > MAX_SIN:  # too flat to hit directly: wander that way and try again later
            s = math.copysign(rng.uniform(0.3, MAX_SIN), s)
        # where on the paddle the ball must land for that angle; keep the paddle on screen
        reach = PW / 2 - 4
        cx = max(-16 + PW / 2, min(864 - PW / 2, x - s / MAX_SIN * reach))
        off = max(-reach, min(reach, x - cx))
        s = off / reach * MAX_SIN
        return SPEED * s, -SPEED * math.sqrt(1 - s * s), off

    t, x, y = 0.0, 424.0, float(BALL_Y)
    vx, vy, off = aim(x)
    paddle.append((0, x - off))
    ball.append((0, x, y))
    t = LAUNCH
    ball.append((t, x, y))
    paddle.append((t, x - off))
    dt = STEP / SPEED
    while True:
        px, py = x, y
        x, y, t = x + vx * dt, y + vy * dt, t + dt
        hit = False
        if x < XMIN or x > XMAX:
            vx, x, hit = -vx, px, True
        if y < YMIN:
            vy, y, hit = -vy, py, True
        if vy > 0 and y >= BALL_Y:   # paddle (it is always in the right spot)
            y = BALL_Y
            ball.append((t, x, y))
            if not lvl or t > PLAY_MAX:
                paddle.append((t, max(-16 + PW / 2, min(864 - PW / 2, x))))  # catch
                break
            vx, vy, off = aim(x)
            paddle.append((t, x - off))
            continue
        w0, d0 = int((x - 2) // 16), int((y - 2) // 16)
        for w in (w0 - 1, w0, w0 + 1):
            for d in (d0 - 1, d0, d0 + 1):
                if (w, d) not in lvl:
                    continue
                cx, cy = 16 * w + 2, 16 * d + 2
                if cx - R <= x <= cx + 12 + R and cy - R <= y <= cy + 12 + R:
                    lvl[w, d] -= 1
                    if lvl[w, d] >= pierce:   # solid brick: bounce off it
                        if cx - R <= px <= cx + 12 + R:
                            vy = -vy
                        else:
                            vx = -vx
                        x, y, hit = px, py, True
                    nxt = f'var(--c{lvl[w, d]})' if lvl[w, d] else 'var(--ce)'
                    fills[w, d] += [(t, 'var(--cs)'), (t + FLASH, nxt)]
                    if not lvl[w, d]:
                        del lvl[w, d]
                    break
            else:
                continue
            break
        if hit:
            ball.append((t, x, y))
    return ball, paddle, fills, len(lvl)


def best_run(grid, seed):
    bricks = sum(1 for col in grid for v in col if v)
    best = None
    for pierce in PIERCES:
        for k in range(SEEDS):
            run = simulate(grid, f'{seed}/{k}', pierce)
            key = (run[3] > bricks * 0.03, run[3], run[0][-1][0])  # (too many left, left, time)
            if best is None or key < best[0]:
                best = key, run, pierce
        if not best[0][0]:
            break
    return best[1], best[2]


def build(grid, seed):
    (ball, paddle, fills, left), pierce = best_run(grid, seed)
    hits = sum(len(s) // 2 for s in fills.values())
    end = ball[-1][0]
    total = round(end + HOLD + REBUILD)
    clock = G.Clock(total)
    # rebuild sweep, left to right
    for (w, d), stops in fills.items():
        lv = grid[w][d]
        at = end + HOLD + w * (REBUILD - 200) / G.WEEKS
        stops += [(at, 'var(--cs)'), (at + 120, f'var(--c{lv})')]
    # ball and paddle glide back to the serve position while the grid rebuilds
    ball += [(end + HOLD, ball[-1][1], ball[-1][2]), (total, ball[0][1], ball[0][2])]
    paddle += [(end + HOLD, paddle[-1][1]), (total, paddle[0][1])]

    cell_css, cell_svg = G.cells_svg(grid, clock, fills)
    bk = G.frames(clock, [(ms, f'transform:translate({x:.1f}px,{y:.1f}px)') for ms, x, y in ball])
    pk = G.frames(clock, [(ms, f'transform:translateX({x - PW / 2:.1f}px)') for ms, x in paddle])
    css = (cell_css +
           f'.ball,.pad{{fill:var(--cs);animation:none {total}ms linear infinite}}'
           f'@keyframes ball{{{bk}}}.ball{{animation-name:ball}}'
           f'@keyframes pad{{{pk}}}.pad{{animation-name:pad}}')
    body = (cell_svg +
            f'<rect class="pad" x="0" y="{PY}" width="{PW}" height="{PH}" rx="3" ry="3"/>'
            f'<circle class="ball" cx="0" cy="0" r="{R}"/>')
    stats = dict(pierce=pierce, total=total, play=round(end), bounces=len(ball), bricks_left=left,
                 hits=hits)
    return css, body, stats


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    grid = G.load_grid()
    css, body, stats = build(grid, seed=sum(v or 0 for col in grid for v in col))
    G.write_svgs(sys.argv[1], sys.argv[2], css, body, 'contribution breakout')
    print('breakout:', stats, file=sys.stderr)


if __name__ == '__main__':
    main()
