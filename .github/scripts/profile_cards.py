"""Generate self-hosted profile cards using only the Python standard library."""
import json
import os
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

API = "https://api.github.com"
def api(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(API + path, data=data, headers={
        "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "profile-cards",
        "Content-Type": "application/json",
    })
    with urlopen(request, timeout=45) as response:
        result = json.load(response)
    if isinstance(result, dict) and result.get("errors"):
        raise RuntimeError(result["errors"])
    return result

def collect(owner):
    repos = []
    page = 1
    while True:
        batch = api(f"/users/{owner}/repos?per_page=100&type=owner&page={page}")
        repos.extend(r for r in batch if not r["fork"] and not r["private"])
        if len(batch) < 100:
            break
        page += 1
    languages = Counter()
    for repo in repos:
        languages.update(api(f"/repos/{repo['full_name']}/languages"))
    query = """query($login:String!) {
      user(login:$login) {
        contributionsCollection {
          startedAt endedAt totalCommitContributions
          totalIssueContributions totalPullRequestContributions
          totalPullRequestReviewContributions
        }
      }
    }"""
    user = api("/graphql", {"query": query, "variables": {"login": owner}})["data"]["user"]
    if user is None:
        raise RuntimeError("GitHub user not found")
    return {"owner": owner, "repositories": len(repos),
            "languages": dict(languages), "activity": user["contributionsCollection"],
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

def render(data, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for theme in ("dark", "light"):
        bg, fg, muted, border, accent = (
            ("#0d1117", "#e6edf3", "#9da7b3", "#30363d", "#7ee787")
            if theme == "dark" else
            ("#ffffff", "#1f2328", "#59636e", "#d1d9e0", "#1a7f37"))
        def text(x, y, value, size=14, color=None, weight=400):
            return f'<text x="{x}" y="{y}" fill="{color or fg}" font-size="{size}" font-weight="{weight}">{escape(str(value))}</text>'
        def card(title, subtitle, body, footer):
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="300" viewBox="0 0 480 300" role="img"><title>{escape(title)}</title><desc>{escape(subtitle+"; "+footer)}</desc><rect x="1" y="1" width="478" height="298" rx="16" fill="{bg}" stroke="{border}"/><g font-family="Segoe UI, Arial, sans-serif">'
            svg += text(24, 35, title, 20, accent, 600) + text(24, 59, subtitle, 12, muted)
            svg += body + text(24, 266, footer, 11, muted) + text(24, 284, "Atualizado: " + data["updated"], 10, muted) + "</g></svg>"
            ET.fromstring(svg)
            return svg
        activity = data["activity"]
        rows = [
            ("Commits", activity["totalCommitContributions"]),
            ("Pull requests", activity["totalPullRequestContributions"]),
            ("Issues", activity["totalIssueContributions"]),
            ("Revisões de código", activity["totalPullRequestReviewContributions"]),
            ("Repositórios públicos próprios", data["repositories"]),
        ]
        body = "".join(text(24, 96+i*31, label) + text(398, 96+i*31, value, 18, accent, 600) for i,(label,value) in enumerate(rows))
        period = activity["startedAt"][:10] + " a " + activity["endedAt"][:10]
        svg = card("Diário de bordo · GitHub", period, body, "Atividade visível ao token do workflow; repositórios sem forks.")
        (directory / f"activity-{theme}.svg").write_text(svg, encoding="utf-8")
        ordered = sorted(data["languages"].items(), key=lambda item: (-item[1], item[0]))
        total = sum(v for _,v in ordered)
        displayed = ordered[:5]
        if len(ordered) > 5:
            displayed.append(("Outras", sum(v for _,v in ordered[5:])))
        colors = ["#7ee787", "#58a6ff", "#d2a8ff", "#f2cc60", "#ff9bce", "#8b949e"]
        body = ""
        for i,(label,value) in enumerate(displayed):
            y = 89+i*28
            percent = value/total*100 if total else 0
            body += text(24, y, label, 12) + text(402, y, f"{percent:.1f}%", 12, muted)
            body += f'<rect x="160" y="{y-10}" width="220" height="9" rx="4" fill="{border}"/><rect x="160" y="{y-10}" width="{220*percent/100:.2f}" height="9" rx="4" fill="{colors[i]}"/>'
        if not total:
            body = text(24, 110, "Nenhum dado de linguagem disponível.", 14, muted)
        svg = card("Linguagens em órbita", "Distribuição por bytes nos repositórios públicos próprios", body, "Sem forks. Volume de código não mede domínio profissional.")
        (directory / f"languages-{theme}.svg").write_text(svg, encoding="utf-8")
    (directory / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

if __name__ == "__main__":
    render(collect(os.environ["PROFILE_OWNER"]), "profile-cards")
