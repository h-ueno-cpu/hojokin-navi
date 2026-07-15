# -*- coding: utf-8 -*-
"""補助金データの鮮度監視スクリプト（GitHub Actions週次実行）。

data/subsidies.json の各制度について:
  1. 公式URLの生存確認（HTTPステータス）
  2. 情報取得日(checkedAt)からの経過日数チェック（90日超は要再調査）
結果を GitHub Actions のジョブサマリー（Markdown）へ出力する。
リンク切れや要再調査があっても異常終了はしない（レポート目的）。
"""
import json
import os
from datetime import date, datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "subsidies.json")
STALE_DAYS = 90
UA = "Mozilla/5.0 (compatible; hojokin-navi-linkcheck/1.0)"


def check_url(url):
    """URLの生存を確認。(ok:bool, status:str) を返す。"""
    for method in ("HEAD", "GET"):
        try:
            req = Request(url, method=method, headers={"User-Agent": UA})
            with urlopen(req, timeout=20) as res:
                return True, str(res.status)
        except HTTPError as e:
            if method == "HEAD" and e.code in (400, 403, 405):
                continue
            return (e.code < 400), str(e.code)
        except (URLError, TimeoutError):
            if method == "HEAD":
                continue
            return False, "ERR:unreachable"
        except Exception as e:
            return False, f"ERR:{type(e).__name__}"
    return False, "ERR:unreachable"


def main():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    subs = data.get("subsidies", [])
    today = date.today()

    dead, stale = [], []
    for s in subs:
        url = s.get("url", "")
        name = f'{s.get("pref","")}{s.get("city","")} {s.get("name","")}'
        if url:
            ok, status = check_url(url)
            if not ok:
                dead.append((name, url, status))
        ca = s.get("checkedAt", "")
        try:
            d = datetime.strptime(ca, "%Y-%m-%d").date()
            if (today - d).days > STALE_DAYS:
                stale.append((name, ca, (today - d).days))
        except ValueError:
            stale.append((name, ca or "(不明)", -1))

    lines = [f"# 補助金データ鮮度チェック（{today.isoformat()}）\n",
             f"- 総件数: {len(subs)}",
             f"- リンク切れ疑い: {len(dead)}",
             f"- 要再調査（{STALE_DAYS}日超未更新）: {len(stale)}\n"]

    if dead:
        lines.append("## リンク切れ疑い（公式ページを確認）\n")
        lines.append("| 制度 | ステータス | URL |")
        lines.append("|---|---|---|")
        for name, url, status in dead:
            lines.append(f"| {name} | {status} | {url} |")
        lines.append("")
    else:
        lines.append("## リンク切れなし\n")

    if stale:
        lines.append(f"## 要再調査（取得から{STALE_DAYS}日超）\n")
        lines.append("| 制度 | 取得日 | 経過日数 |")
        lines.append("|---|---|---|")
        for name, ca, days in sorted(stale, key=lambda x: -x[2]):
            lines.append(f"| {name} | {ca} | {'不正' if days < 0 else days} |")
        lines.append("")

    report = "\n".join(lines)
    print(report)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report + "\n")

    # リンク切れ件数を後続ステップ用に出力
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"dead_count={len(dead)}\n")


if __name__ == "__main__":
    main()
