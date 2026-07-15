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
# 自治体サーバはデータセンターIP・簡易UAを弾くことがあるため、ブラウザ相当のヘッダを送る
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.7",
}
# ボット遮断で返りがちなコード（真のリンク切れと断定せず「要確認」に回す）
SOFT_BLOCK = {400, 403, 404, 406, 429}


def check_url(url):
    """URLの生存を確認。(ok:bool, status:str, soft:bool) を返す。
    soft=True は自動判定不可（ボット遮断の疑い）で、リンク切れ断定を避ける。"""
    last = "ERR:unreachable"
    for method in ("GET", "HEAD"):
        try:
            req = Request(url, method=method, headers=HEADERS)
            with urlopen(req, timeout=25) as res:
                return True, str(res.status), False
        except HTTPError as e:
            last = str(e.code)
            if e.code in SOFT_BLOCK:
                return False, last, True
            return (e.code < 400), last, False
        except (URLError, TimeoutError):
            last = "ERR:unreachable"
            continue
        except Exception as e:
            return False, f"ERR:{type(e).__name__}", True
    return False, last, True


def main():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    subs = data.get("subsidies", [])
    today = date.today()

    dead, softng, stale = [], [], []
    for s in subs:
        url = s.get("url", "")
        name = f'{s.get("pref","")}{s.get("city","")} {s.get("name","")}'
        if url:
            ok, status, soft = check_url(url)
            if not ok:
                (softng if soft else dead).append((name, url, status))
        ca = s.get("checkedAt", "")
        try:
            d = datetime.strptime(ca, "%Y-%m-%d").date()
            if (today - d).days > STALE_DAYS:
                stale.append((name, ca, (today - d).days))
        except ValueError:
            stale.append((name, ca or "(不明)", -1))

    lines = [f"# 補助金データ鮮度チェック（{today.isoformat()}）\n",
             f"- 総件数: {len(subs)}",
             f"- リンク切れ（要対応）: {len(dead)}",
             f"- 要確認（自動判定不可・ボット遮断の疑い）: {len(softng)}",
             f"- 要再調査（{STALE_DAYS}日超未更新）: {len(stale)}\n"]

    if dead:
        lines.append("## リンク切れ（公式ページの移動・終了の疑い。要対応）\n")
        lines.append("| 制度 | ステータス | URL |")
        lines.append("|---|---|---|")
        for name, url, status in dead:
            lines.append(f"| {name} | {status} | {url} |")
        lines.append("")
    else:
        lines.append("## リンク切れなし\n")

    if softng:
        lines.append("## 要確認（CIから自動確認できず・手元ブラウザで開いて確認）\n")
        lines.append("| 制度 | ステータス | URL |")
        lines.append("|---|---|---|")
        for name, url, status in softng:
            lines.append(f"| {name} | {status} | {url} |")
        lines.append("")

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
