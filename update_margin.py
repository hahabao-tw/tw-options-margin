#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_margin.py
----------------
自動從臺灣期貨交易所抓取「股價指數類保證金一覽表」，
解析「臺指選擇權風險保證金 A / B / C 值」的【原始保證金】，
並寫入 margin_data.json，供前端網頁讀取。

設計原則：
  * 只用 Python 標準函式庫（stdlib），不需安裝任何套件。
  * 抓取失敗時「保留舊資料」，絕不用壞資料覆蓋 margin_data.json。
  * 來源資料為 CSV（Big5 / cp950 編碼），比解析 HTML 穩定。

資料來源：
  CSV 下載：https://www.taifex.com.tw/cht/5/indexMargingDown
  網頁版　：https://www.taifex.com.tw/cht/5/indexMarging
"""

import json
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 期交所「股價指數類保證金」CSV 下載網址
CSV_URL = "https://www.taifex.com.tw/cht/5/indexMargingDown"

# 輸出檔案（與本腳本同目錄）
OUTPUT_FILE = Path(__file__).resolve().parent / "margin_data.json"

# 台北時區（UTC+8）
TPE = timezone(timedelta(hours=8))


def fetch_csv_text():
    """下載 CSV 並解碼為文字。期交所下載端點需要 Referer，否則可能回傳錯誤頁。"""
    req = urllib.request.Request(
        CSV_URL,
        headers={
            # 沒有 Referer 時，期交所有時會回傳 HTML 錯誤頁而非 CSV
            "Referer": "https://www.taifex.com.tw/cht/5/indexMarging",
            "User-Agent": "Mozilla/5.0 (compatible; MarginBot/1.0)",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    # 期交所 CSV 為 Big5 / cp950 編碼
    return raw.decode("cp950", errors="replace")


def normalize(text):
    """把全形括號轉成半形，方便比對 (A) (B) (C)。"""
    return text.replace("（", "(").replace("）", ")").strip()


def parse_margin(csv_text):
    """
    解析 CSV，回傳 dict：
      {
        "update_date": "2026/06/18",
        "txo": {"A": 169000, "B": 85000, "C": 17000}
      }
    取用欄位：原始保證金（CSV 第 4 欄，index = 3）。
    """
    update_date = ""
    result = {"A": None, "B": None, "C": None}

    for line in csv_text.splitlines():
        line = line.strip()
        if not line:
            continue

        # 第一行通常是「更新日期:2026/06/18」
        if "更新日期" in line:
            # 取冒號（全形或半形）後面的日期字串
            for sep in ("：", ":"):
                if sep in line:
                    update_date = line.split(sep, 1)[1].strip()
                    break
            continue

        cols = [c.strip() for c in line.split(",")]
        if len(cols) < 4:
            continue

        name = normalize(cols[0])
        # 只取「臺指選擇權風險保證金(X)值」這幾列
        if "臺指選擇權風險保證金" not in name:
            continue

        # 原始保證金 = 第 4 欄（index 3）
        raw_value = cols[3].replace(",", "").strip()
        if not raw_value.isdigit():
            continue
        value = int(raw_value)

        if "(A)" in name:
            result["A"] = value
        elif "(B)" in name:
            result["B"] = value
        elif "(C)" in name:
            result["C"] = value

    # A、B 一定要有；C 若為 0 期交所可能不列（依官方註記），預設為 0
    if result["A"] is None or result["B"] is None:
        raise ValueError("找不到臺指選擇權 A 值或 B 值，CSV 格式可能改變")
    if result["C"] is None:
        result["C"] = 0

    return {"update_date": update_date, "txo": result}


def main():
    try:
        csv_text = fetch_csv_text()
        parsed = parse_margin(csv_text)
    except Exception as e:
        # 抓取或解析失敗：保留舊檔，不覆蓋，並以非零碼結束讓 Actions 顯示警告
        print(f"[錯誤] 更新失敗，保留現有 margin_data.json：{e}", file=sys.stderr)
        sys.exit(1)

    parsed["fetched_at"] = datetime.now(TPE).strftime("%Y-%m-%d %H:%M:%S %z")

    new_text = json.dumps(parsed, ensure_ascii=False, indent=2)

    # 若內容與舊檔完全相同（除了 fetched_at），仍會更新時間戳，這沒關係。
    OUTPUT_FILE.write_text(new_text + "\n", encoding="utf-8")
    print("[成功] 已更新 margin_data.json")
    print(new_text)


if __name__ == "__main__":
    main()
