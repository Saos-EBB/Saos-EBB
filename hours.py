"""Render a 'when do I commit' 24-hour bar chart as light and dark SVG.

Usage: python hours.py OUT_DIR   -> OUT_DIR/hours.svg, OUT_DIR/hours-dark.svg
Env:   STATS_TOKEN (or GITHUB_TOKEN), GITHUB_REPOSITORY_OWNER (default Saos-EBB),
       HOURS_MONTHS (default 6). Stdlib only.
"""
import random, base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = 'https://api.github.com'
TZ_NAME = 'Europe/Vienna'


# ---------------------------------------------------------------- GitHub API

def _request(url, token):
    req = urllib.request.Request(url, headers={
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'profile-hours-chart',
        **({'Authorization': f'Bearer {token}'} if token else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r), r.headers.get('Link', '')


def _next_link(link):
    for part in link.split(','):
        seg = part.split(';')
        if len(seg) > 1 and 'rel="next"' in seg[1]:
            return seg[0].strip()[1:-1]
    return None


def paginate(url, token):
    while url:
        data, link = _request(url, token)
        yield from data
        url = _next_link(link)


def list_repos(login, token):
    try:
        return list(paginate(f'{API}/user/repos?affiliation=owner,collaborator&per_page=100', token))
    except urllib.error.HTTPError as e:
        if e.code not in (401, 403):
            raise
        print(f'/user/repos -> {e.code}, falling back to /users/{login}/repos')
        return list(paginate(f'{API}/users/{login}/repos?type=owner&per_page=100', token))


def collect_dates(login, token, since):
    repos = [r for r in list_repos(login, token) if not r.get('fork')]
    seen, dates, scanned = set(), [], 0
    q = urllib.parse.urlencode({'author': login, 'since': since, 'per_page': 100})
    for repo in repos:
        full = repo['full_name']
        try:
            commits = list(paginate(f'{API}/repos/{full}/commits?{q}', token))
        except urllib.error.HTTPError as e:
            if e.code in (409, 404, 403, 451):  # empty, gone, blocked
                continue
            raise
        scanned += 1
        for c in commits:
            if c['sha'] in seen:
                continue
            seen.add(c['sha'])
            dates.append(c['commit']['author']['date'])
    return scanned, dates


# ---------------------------------------------------------------- timezone

def _last_sunday(year, month):
    d = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _vienna_fallback(dt):
    """CET/CEST rule: +2 from last Sunday of March 01:00 UTC to last Sunday of October 01:00 UTC."""
    start = _last_sunday(dt.year, 3).replace(hour=1)
    end = _last_sunday(dt.year, 10).replace(hour=1)
    return dt + timedelta(hours=2 if start <= dt < end else 1)


try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(TZ_NAME)
except Exception:  # no zoneinfo / no tzdata (e.g. Windows without the tzdata package)
    _TZ = None


def local_hour(iso):
    dt = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(timezone.utc)
    return (dt.astimezone(_TZ) if _TZ else _vienna_fallback(dt)).hour


# ---------------------------------------------------------------- SVG

THEMES = {  # (text colour, muted colour)
    'light': ('#57606a', '#8c959f'),
    'dark': ('#c9d1d9', '#8b949e'),
}
# same hues and levels as the contribution grid in gol.py (PALETTES dots, low -> high)
HUES = {
    'light': {'blau': ('#bfdbfe', '#60a5fa', '#2563eb', '#1e3a8a'),
              'pink': ('#fbcfe8', '#f472b6', '#db2777', '#9d174d'),
              'lila': ('#e9d5ff', '#c084fc', '#9333ea', '#6b21a8')},
    'dark': {'blau': ('#172554', '#1e40af', '#3b82f6', '#93c5fd'),
             'pink': ('#500724', '#9d174d', '#ec4899', '#f9a8d4'),
             'lila': ('#3b0764', '#6b21a8', '#a855f7', '#d8b4fe')},
}
EMPTY = {'light': '#ebedf0', 'dark': '#161b22'}
W, H = 880, 200
PAD_X, TOP, BASE = 20, 44, 168
BAR_MAX = BASE - TOP


def font_css():
    here = os.path.dirname(os.path.abspath(__file__))
    data = base64.b64encode(open(f'{here}/fonts/jetbrains-mono-latin.woff2', 'rb').read()).decode()
    return f"@font-face{{font-family:jbm;src:url(data:font/woff2;base64,{data}) format('woff2')}}"


def render(counts, months, theme, font, hues):
    text, muted = THEMES[theme]
    top = max(counts) or 1
    peak = counts.index(max(counts))
    slot = (W - 2 * PAD_X) / 24
    bw = slot * 0.7
    bars, labels = [], []
    for h, n in enumerate(counts):
        frac = n / top
        bh = max(2.0, BAR_MAX * frac) if n else 2.0
        x = PAD_X + h * slot + (slot - bw) / 2
        # level 1-4 like a contribution cell, hue rolled per bar like the grid
        fill = HUES[theme][hues[h]][min(3, int(frac * 4))] if n else EMPTY[theme]
        bars.append(f'<rect class="b" style="animation-delay:{h * 40}ms" x="{x:.1f}" y="{BASE - bh:.1f}" '
                    f'width="{bw:.1f}" height="{bh:.1f}" rx="2" fill="{fill}">'
                    f'<title>{h:02d}:00 · {n} commits</title></rect>')
        if h % 3 == 0:
            labels.append(f'<text x="{x + bw / 2:.1f}" y="{BASE + 20}" text-anchor="middle">{h:02d}</text>')
    title = f'commits by hour · last {months} months · {TZ_NAME}'
    note = f'peak {peak:02d}:00 · {counts[peak]} commits' if counts[peak] else 'no commits'
    css = (font +
           f'text{{font-family:jbm,ui-monospace,monospace;font-size:12px;fill:{muted}}}'
           f'.t{{font-size:13px;fill:{text}}}'
           '.b{transform-box:fill-box;transform-origin:50% 100%;'
           'animation:grow .7s cubic-bezier(.2,.8,.3,1) both}'
           '@keyframes grow{from{transform:scaleY(0);opacity:0}to{transform:scaleY(1);opacity:1}}'
           '@media (prefers-reduced-motion:reduce){.b{animation:none}}')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
            f'role="img" aria-label="{title}; {note}">'
            f'<style>{css}</style>'
            f'<text class="t" x="{PAD_X}" y="22">{title}</text>'
            f'<text x="{W - PAD_X}" y="22" text-anchor="end">{note}</text>'
            f'<line x1="{PAD_X}" y1="{BASE + 0.5}" x2="{W - PAD_X}" y2="{BASE + 0.5}" stroke="{muted}" stroke-opacity=".35"/>'
            + ''.join(bars) + ''.join(labels) + '</svg>\n')


# ---------------------------------------------------------------- main

def main():
    if len(sys.argv) != 2:
        sys.exit('usage: python hours.py OUT_DIR')
    out = sys.argv[1]
    token = os.environ.get('STATS_TOKEN') or os.environ.get('GITHUB_TOKEN')
    login = os.environ.get('GITHUB_REPOSITORY_OWNER') or 'Saos-EBB'
    months = int(os.environ.get('HOURS_MONTHS') or 6)
    since = (datetime.now(timezone.utc) - timedelta(days=round(months * 30.437))).strftime('%Y-%m-%dT%H:%M:%SZ')

    scanned, dates = collect_dates(login, token, since)
    counts = [0] * 24
    for d in dates:
        counts[local_hour(d)] += 1

    os.makedirs(out, exist_ok=True)
    font = font_css()
    rng = random.SystemRandom()
    hues = [rng.choice(list(HUES['light'])) for _ in range(24)]  # same roll for light and dark
    for theme, name in (('light', 'hours.svg'), ('dark', 'hours-dark.svg')):
        with open(os.path.join(out, name), 'w', encoding='utf-8', newline='\n') as f:
            f.write(render(counts, months, theme, font, hues))

    peak = counts.index(max(counts))
    print(f'login {login} | since {since} | tz {"zoneinfo" if _TZ else "fallback CET/CEST"}')
    print(f'repos scanned: {scanned} | commits counted: {len(dates)}')
    print('per hour: ' + ' '.join(f'{h:02d}:{n}' for h, n in enumerate(counts)))
    print(f'peak: {peak:02d}:00 ({counts[peak]})')


if __name__ == '__main__':
    main()
