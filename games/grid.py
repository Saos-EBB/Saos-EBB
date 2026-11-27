"""Contribution grid + shared SVG plumbing for the grid games (stdlib only).

Grid format: list of 53 weeks, each a list of 7 days (Sunday first) holding the
contribution level 0..4, or None for days that do not exist (the future part of
the current week), exactly like Platane/snk leaves those cells out."""
import json, os, random, urllib.request

WEEKS, DAYS = 53, 7
LEVELS = {'NONE': 0, 'FIRST_QUARTILE': 1, 'SECOND_QUARTILE': 2, 'THIRD_QUARTILE': 3, 'FOURTH_QUARTILE': 4}

QUERY = ('query($l:String!){user(login:$l){contributionsCollection{contributionCalendar'
         '{weeks{contributionDays{contributionLevel weekday}}}}}}')


def fetch_grid(login, token):
    req = urllib.request.Request('https://api.github.com/graphql',
        json.dumps({'query': QUERY, 'variables': {'l': login}}).encode(),
        {'Authorization': f'bearer {token}', 'Content-Type': 'application/json'})
    data = json.load(urllib.request.urlopen(req, timeout=30))
    if data.get('errors'):
        raise RuntimeError(data['errors'])
    weeks = data['data']['user']['contributionsCollection']['contributionCalendar']['weeks']
    grid = []
    for wk in weeks[-WEEKS:]:
        col = [None] * DAYS
        for d in wk['contributionDays']:
            col[d['weekday']] = LEVELS[d['contributionLevel']]
        grid.append(col)
    while len(grid) < WEEKS:  # very young accounts: pad on the left with empty weeks
        grid.insert(0, [0] * DAYS)
    return grid


def fake_grid(seed=0):
    """Plausible random calendar: busy streaks, quiet weeks, partial last week."""
    rng = random.Random(seed)
    grid, mood = [], 0.5
    for w in range(WEEKS):
        mood = min(1, max(0, mood + rng.uniform(-0.3, 0.3)))
        col = []
        for d in range(DAYS):
            weekend = d in (0, 6)
            p = mood * (0.5 if weekend else 1)
            col.append(0 if rng.random() > p else rng.choices([1, 2, 3, 4], [4, 3, 2, 1])[0])
        grid.append(col)
    cut = rng.randrange(1, DAYS)
    grid[-1] = grid[-1][:cut] + [None] * (DAYS - cut)
    return grid


def load_grid():
    token = os.environ.get('GITHUB_TOKEN')
    login = os.environ.get('GITHUB_REPOSITORY_OWNER') or 'Saos-EBB'
    if token:
        return fetch_grid(login, token)
    return fake_grid(login)


def cell_xy(week, day):
    return 16 * week + 2, 16 * day + 2


# ---------------------------------------------------------------- SVG output

LIGHT = '--cb:#1b1f230a;--cs:#db2777;--ce:#ebedf0;--c1:#fbcfe8;--c2:#f472b6;--c3:#db2777;--c4:#9d174d'
DARK = '--cb:#1b1f230a;--cs:#fbcfe8;--ce:#161b22;--c1:#500724;--c2:#9d174d;--c3:#ec4899;--c4:#f9a8d4'


class Clock:
    """Formats ms as keyframe percentages on a fixed 0.001% grid."""
    def __init__(self, total):
        self.total = total

    def q(self, ms):  # quantize to the percentage grid (in thousandths of a percent)
        return max(0, min(100000, round(ms / self.total * 100000)))

    @staticmethod
    def fmt(q):
        return f'{q / 1000:.3f}'.rstrip('0').rstrip('.') + '%'

    def pct(self, ms):
        return self.fmt(self.q(ms))


def frames(clock, stops):
    """stops: [(ms, body)] in time order -> keyframe text. Consecutive equal bodies are
    merged into one selector list, stops landing on the same percentage keep the last."""
    by_q = {}
    for ms, body in stops:
        by_q[clock.q(ms)] = body
    out, sel, prev = [], [], None
    for q in sorted(by_q):
        body = by_q[q]
        if body != prev and sel:
            out.append(f'{",".join(sel)}{{{prev}}}')
            sel = []
        sel.append(clock.fmt(q))
        prev = body
    if sel:
        out.append(f'{",".join(sel)}{{{prev}}}')
    return ''.join(out)


def cells_svg(grid, clock, fills):
    """fills: {(week, day): [(ms, 'var(--cN)'|...), ...]} change list per cell (first entry at 0).
    Emits snk-compatible cells: `@keyframes cX{..}.c.cX{fill:var(--cN);animation-name:cX}` and
    `<rect class="c cX" x y ...>`; identical animations share one keyframes block."""
    css = [f'.c{{shape-rendering:geometricPrecision;fill:var(--ce);stroke-width:1px;stroke:var(--cb);'
           f'animation:none {clock.total}ms step-end infinite;width:12px;height:12px}}']
    rects, names = [], {}
    for w, col in enumerate(grid):
        for d, lvl in enumerate(col):
            if lvl is None:
                continue
            x, y = cell_xy(w, d)
            cls = 'c'
            if lvl:
                stops = fills.get((w, d)) or [(0, f'var(--c{lvl})')]
                body = frames(clock, [(ms, f'fill:{f}') for ms, f in stops] + [(clock.total, f'fill:var(--c{lvl})')])
                if body not in names:
                    names[body] = f'c{len(names):x}'
                    css.append(f'@keyframes {names[body]}{{{body}}}'
                               f'.c.{names[body]}{{fill:var(--c{lvl});animation-name:{names[body]}}}')
                cls = f'c {names[body]}'
            rects.append(f'<rect class="{cls}" x="{x}" y="{y}" width="12" height="12" rx="2" ry="2"/>')
    return ''.join(css), ''.join(rects)


def write_svgs(out_light, out_dark, css, body, desc):
    for path, root in ((out_light, LIGHT), (out_dark, DARK)):
        svg = (f'<svg viewBox="-16 -32 880 192" width="880" height="192" xmlns="http://www.w3.org/2000/svg">'
               f'<desc>{desc}</desc><style>:root{{{root}}}{css}</style>{body}</svg>')
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(svg)
