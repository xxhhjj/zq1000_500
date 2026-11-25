# -*- coding: utf-8 -*-
"""
从东方财富拉取中证1000(000852) / 中证500(000905) 全量日线，生成 data.json。
供 GitHub Actions 每交易日收盘后自动运行；本地也可直接执行。

数据源页面: https://quote.eastmoney.com/center/hszs.html
数据接口:   https://push2his.eastmoney.com/api/qt/stock/kline/get
"""
import json
import os
import sys
import time
import urllib.request
import ssl
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data.json")

INDEX_A = ("000852", "中证1000")
INDEX_B = ("000905", "中证500")
# GitHub Actions(Ubuntu) 上 https 正常；本机 Windows 上 https 有 SSL 重协商问题，用 http 兜底
SCHEMES = ["https", "http"]

API = ("{scheme}://push2his.eastmoney.com/api/qt/stock/kline/get?"
       "secid=1.{code}&klt=101&fqt=1&beg=0&end=20500101&lmt=100000"
       "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def fetch(code, name):
    last = None
    for scheme in SCHEMES:
        url = API.format(scheme=scheme, code=code)
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://quote.eastmoney.com/center/hszs.html",
                })
                with urllib.request.urlopen(req, timeout=45, context=CTX) as r:
                    js = json.loads(r.read().decode("utf-8"))
                d = js.get("data") or {}
                klines = d.get("klines") or []
                if js.get("rc") != 0 or not klines:
                    raise ValueError("empty klines: rc=%s" % js.get("rc"))
                bars = {}
                for line in klines:
                    p = line.split(",")
                    v = float(p[2])  # 索引2 = 收盘价
                    if v > 0:
                        bars[p[0]] = v
                print("%s %s: %d bars (%s -> %s) via %s" %
                      (code, name, len(bars), min(bars), max(bars), scheme))
                return bars
            except Exception as e:
                last = e
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("fetch %s failed: %s" % (code, last))


def main():
    a = fetch(*INDEX_A)
    b = fetch(*INDEX_B)
    dates = sorted(set(a) & set(b))
    if len(dates) < 100:
        raise RuntimeError("too few aligned bars: %d" % len(dates))

    rows = []
    for d in dates:
        pa, pb = a[d], b[d]
        rows.append({
            "d": d,
            "a": round(pa, 2),
            "b": round(pb, 2),
            "s": round(pa - pb, 2),
            "r": round(pa / pb, 6),
        })

    payload = {
        "meta": {
            "source": "东方财富网 · 沪深指数行情中心",
            "sourceUrl": "https://quote.eastmoney.com/center/hszs.html",
            "api": "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bars": len(rows),
            "start": rows[0]["d"],
            "end": rows[-1]["d"],
            "note": "日线收盘价；每交易日收盘后由 GitHub Actions 自动更新",
        },
        "names": {"a": INDEX_A[1], "b": INDEX_B[1]},
        "codes": {"a": INDEX_A[0], "b": INDEX_B[0]},
        "data": rows,
    }

    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUT)

    last = rows[-1]
    print("wrote %s | %d bars | %s -> %s | 价差 %.2f 比价 %.4f" %
          (OUT, len(rows), rows[0]["d"], last["d"], last["s"], last["r"]))
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        print("last row:", last)


if __name__ == "__main__":
    main()
