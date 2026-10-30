"""Post-process snk SVGs: drop the progress bar, then play Conway's Game of Life
on the contribution grid once the snake is done. Usage: python3 gol.py dist/*.svg"""
import base64, random, re, sys, datetime, json, os, urllib.request

GENS = 40          # generations to play
STEP = 200         # ms per generation
HOLD = 1500        # ms to hold the last generation before the loop restarts
DENSITY = 0.3      # top up the seed with random cells up to this density

def commit_stats():
    """All-time commit stats via GraphQL: (public commits, private contributions, per day)."""
    token, login = os.environ.get('GITHUB_TOKEN'), os.environ.get('GITHUB_REPOSITORY_OWNER')
    if not token or not login:
        return None
    def gql(query, **variables):
        req = urllib.request.Request('https://api.github.com/graphql',
            json.dumps({'query': query, 'variables': variables}).encode(),
            {'Authorization': f'bearer {token}'})
        return json.load(urllib.request.urlopen(req))['data']['user']
    created = gql('query($l:String!){user(login:$l){createdAt}}', l=login)['createdAt']
    start = datetime.datetime.fromisoformat(created.replace('Z', '+00:00'))
    now = datetime.datetime.now(datetime.timezone.utc)
    pub = priv = 0
    frm = start
    while frm < now:  # the API only allows windows of up to one year
        to = min(frm + datetime.timedelta(days=365), now)
        c = gql('query($l:String!,$f:DateTime!,$t:DateTime!){user(login:$l){contributionsCollection(from:$f,to:$t)'
                '{totalCommitContributions restrictedContributionsCount}}}',
                l=login, f=frm.isoformat(), t=to.isoformat())['contributionsCollection']
        pub += c['totalCommitContributions']
        priv += c['restrictedContributionsCount']
        frm = to
    return pub, priv, (pub + priv) / max(1, (now - start).days)

LANGS = [  # total, public, private, per day
    '[ {} commits · {} public · {} private · Ø {}/day ]',
    '[ {} Commits · {} öffentlich · {} privat · Ø {}/Tag ]',
    '[ {} commits · {} públicos · {} privados · Ø {}/día ]',
    '[ {} commits · {} publics · {} privés · Ø {}/jour ]',
    '[ {} commits · {} públicos · {} privados · Ø {}/dia ]',
    '[ {} commit · {} pubblici · {} privati · Ø {}/giorno ]',
    '[ {} коммитов · {} публичных · {} приватных · Ø {}/день ]',
    '[ {} commitów · {} publicznych · {} prywatnych · Ø {}/dzień ]',
    '[ {} commit · {} herkese açık · {} gizli · Ø {}/gün ]',
    '[ {} commits · {} openbaar · {} privé · Ø {}/dag ]',
]
TYPE, DELETE, PAUSE, GAP = 55, 25, 2500, 300  # ms per typed char, per deleted char, hold, gap

def _font_css():
    ranges = {  # unicode ranges as published by @fontsource/jetbrains-mono
        'latin': 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD',
        'latin-ext': 'U+0100-02AF,U+0304,U+0308,U+0329,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF',
        'cyrillic': 'U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116',
    }
    here = os.path.dirname(os.path.abspath(__file__))
    css = ''
    for name, rng in ranges.items():
        data = base64.b64encode(open(f'{here}/fonts/jetbrains-mono-{name}.woff2', 'rb').read()).decode()
        css += f"@font-face{{font-family:jbm;src:url(data:font/woff2;base64,{data}) format('woff2');unicode-range:{rng}}}"
    return css
FONT_CSS = _font_css()

INTRO = [
    "Hey, I'm Kev. Developer from Austria.",
    'Hey, ich bin Kev. Developer aus Österreich.',
    'Hola, soy Kev. Desarrollador de Austria.',
    "Salut, je suis Kev. Développeur d'Autriche.",
    'Olá, eu sou o Kev. Desenvolvedor da Áustria.',
    "Ciao, sono Kev. Sviluppatore dall'Austria.",
    'Привет, я Кев. Разработчик из Австрии.',
    'Cześć, jestem Kev. Programista z Austrii.',
    "Merhaba, ben Kev. Avusturya'dan geliştirici.",
    'Hoi, ik ben Kev. Developer uit Oostenrijk.',
]

def typed(key, line, cx, y, size, a, c, cycle):
    """One line typed in from a, held, deleted from c; returns (css, svg)."""
    pct = lambda ms: f'{ms / cycle * 100:.3f}'.rstrip('0').rstrip('.') + '%'
    n, w = len(line), len(line) * size * 0.6  # JetBrains Mono advance is 0.6em
    x0, b, d = cx - w / 2, a + n * TYPE, c + n * DELETE
    # clip grows char by char, holds, shrinks char by char; cursor follows its edge
    css = (f'@keyframes c{key}{{0%,{pct(a)}{{transform:scaleX(0);animation-timing-function:steps({n},end)}}'
           f'{pct(b)},{pct(c)}{{transform:scaleX(1);animation-timing-function:steps({n},end)}}'
           f'{pct(d)},100%{{transform:scaleX(0)}}}}.c{key}{{animation-name:c{key}}}'
           f'@keyframes k{key}{{0%,{pct(a)}{{opacity:0}}{pct(a)}{{opacity:1;transform:translateX(0);animation-timing-function:steps({n},end)}}'
           f'{pct(b)},{pct(c)}{{opacity:1;transform:translateX({w:.1f}px);animation-timing-function:steps({n},end)}}'
           f'{pct(d)}{{opacity:1;transform:translateX(0)}}{pct(d + 1)},100%{{opacity:0}}}}.k{key}{{animation-name:k{key}}}')
    svg = (f'<clipPath id="p{key}"><rect class="tc c{key}" x="{x0:.1f}" y="{y - size}" width="{w:.1f}" height="{size + 4}"/></clipPath>'
           f'<text class="tt" font-size="{size}" x="{x0:.1f}" y="{y}" clip-path="url(#p{key})">{line}</text>'
           f'<rect class="tk k{key}" x="{x0:.1f}" y="{y - size + 1}" width="2" height="{size + 2}" opacity="0"/>')
    return css, svg

def typing(cx, top_y, bottom_y, bottom_lines):
    """Per language: intro types in and holds; then intro deletes while the counter types in;
    counter holds and deletes; only then the next language starts."""
    plan, t = [], 0
    for i, top in enumerate(INTRO):
        c1 = t + len(top) * TYPE + PAUSE
        plan.append((f't{i}', top, top_y, 22, t, c1))
        t = c1 + len(top) * DELETE
        if bottom_lines:
            bot = bottom_lines[i]
            c2 = c1 + len(bot) * TYPE + PAUSE
            plan.append((f'b{i}', bot, bottom_y, 13, c1, c2))
            t = max(t, c2 + len(bot) * DELETE)
        t += GAP
    css = (f'.tt{{font-family:jbm,ui-monospace,monospace;fill:var(--c4);white-space:pre}}'
           f'.tc,.tk{{transform-box:fill-box;transform-origin:0 0;animation:none {t}ms infinite}}.tk{{fill:var(--cs)}}')
    out = ''
    for key, line, y, size, a, c in plan:
        c_, s_ = typed(key, line, cx, y, size, a, c, t)
        css += c_
        out += s_
    return f'<style>{css}</style>' + out

PALETTES = {  # (snake, 4 dot levels low -> high) for light and dark mode
    'blau': (('#2563eb', '#bfdbfe', '#60a5fa', '#2563eb', '#1e3a8a'), ('#bfdbfe', '#172554', '#1e40af', '#3b82f6', '#93c5fd')),
    'pink': (('#db2777', '#fbcfe8', '#f472b6', '#db2777', '#9d174d'), ('#fbcfe8', '#500724', '#9d174d', '#ec4899', '#f9a8d4')),
    'lila': (('#9333ea', '#e9d5ff', '#c084fc', '#9333ea', '#6b21a8'), ('#e9d5ff', '#3b0764', '#6b21a8', '#a855f7', '#d8b4fe')),
}
PALETTE = random.SystemRandom().choice(list(PALETTES))

def recolor(svg, dark):
    snake, *dots = PALETTES[PALETTE][dark]
    svg = re.sub(r'--cs:#\w+', f'--cs:{snake}', svg, count=1)
    for i, c in enumerate(dots, 1):
        svg = re.sub(rf'--c{i}:#\w+', f'--c{i}:{c}', svg, count=1)
    return svg

def stats_lines(stats):
    pub, priv, avg = stats
    return [l.format(pub + priv, pub, priv, f'{avg:.1f}') for l in LANGS]

def process(path, stats):
    svg = recolor(open(path).read(), 'dark' in path)

    # 1. remove the progress bar and crop it out of the viewBox
    svg = re.sub(r'<rect class="u[^"]*"[^>]*/>', '', svg)
    vx, vy, vw, vh = map(float, re.search(r'viewBox="([^"]+)"', svg).group(1).split())
    bottom = max(int(y) for y in re.findall(r'<rect class="c[^"]*" x="\d+" y="(\d+)"', svg)) + 12 + 16
    text_y = bottom + 8
    vy -= 44  # room for the intro line above the grid
    intro_y = vy + 30
    if stats:
        bottom += 24
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

    # hide the snake while the game of life runs
    css.append(f'@keyframes sn{{0%{{opacity:1}}{pct(t)},100%{{opacity:0}}}}.sn{{animation:sn {total}ms step-end infinite}}')

    svg = svg.replace('</style>', ''.join(css) + '</style>', 1)
    first_snake = svg.index('<rect class="s')
    svg = svg[:first_snake] + ''.join(rects) + '<g class="sn">' + svg[first_snake:].replace('</svg>', '</g></svg>')
    # intro above the grid, commit counter below it, typed out in different languages
    svg = svg.replace('<g class="sn">', typing(vx + vw / 2, intro_y, text_y, stats and stats_lines(stats)) + '<g class="sn">', 1)
    svg = svg.replace('</style>', FONT_CSS + '</style>', 1)
    open(path, 'w').write(svg)

stats = commit_stats()
for f in sys.argv[1:]:
    process(f, stats)
