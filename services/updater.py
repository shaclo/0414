# ============================================================
# services/updater.py
# GitHub Release 自动更新检查 + 下载 + 解压
# ============================================================

import os
import sys
import json
import shutil
import zipfile
import tempfile
from pathlib import Path
from packaging.version import Version

from PySide6.QtCore import QThread, Signal
import urllib.request
import urllib.error


class UpdateChecker(QThread):
    """检查 GitHub 最新 Release 版本"""
    result = Signal(dict)   # {"has_update": bool, "latest_version": str, "download_url": str, "release_notes": str}
    error = Signal(str)

    def __init__(self, api_url: str, current_version: str):
        super().__init__()
        self.api_url = api_url
        self.current_version = current_version

    def run(self):
        try:
            req = urllib.request.Request(
                self.api_url,
                headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "NarrativeLoom-Updater"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            tag = data.get("tag_name", "").lstrip("vV")
            if not tag:
                self.result.emit({"has_update": False, "latest_version": "", "download_url": "", "release_notes": ""})
                return

            has_update = Version(tag) > Version(self.current_version)

            # 找 zip 资产（source code zip 或自定义 zip）
            download_url = ""
            assets = data.get("assets", [])
            for asset in assets:
                if asset.get("name", "").endswith(".zip"):
                    download_url = asset["browser_download_url"]
                    break
            if not download_url:
                download_url = data.get("zipball_url", "")

            self.result.emit({
                "has_update": has_update,
                "latest_version": tag,
                "download_url": download_url,
                "release_notes": data.get("body", "") or "无更新说明",
            })
        except Exception as e:
            self.error.emit(f"检查更新失败: {e}")


class UpdateDownloader(QThread):
    """下载并解压更新包"""
    progress = Signal(int, str)   # (percent, message)
    finished = Signal(bool, str)  # (success, message)

    def __init__(self, download_url: str, target_dir: str):
        super().__init__()
        self.download_url = download_url
        self.target_dir = target_dir

    def run(self):
        try:
            self.progress.emit(5, "正在连接下载服务器…")

            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": "NarrativeLoom-Updater"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 8192

                tmp_dir = os.path.join(self.target_dir, "_update_tmp")
                os.makedirs(tmp_dir, exist_ok=True)
                zip_path = os.path.join(tmp_dir, "update.zip")

                with open(zip_path, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = min(int(downloaded / total * 70), 70)
                            self.progress.emit(10 + pct, f"下载中… {downloaded // 1024}KB / {total // 1024}KB")
                        else:
                            self.progress.emit(40, f"下载中… {downloaded // 1024}KB")

            self.progress.emit(80, "正在解压更新包…")

            # 解压
            extract_dir = os.path.join(tmp_dir, "extracted")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            # GitHub zipball 会有一层目录包裹，找到实际内容根
            entries = os.listdir(extract_dir)
            if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
                source_dir = os.path.join(extract_dir, entries[0])
            else:
                source_dir = extract_dir

            self.progress.emit(85, "正在更新文件…")

            # 需要跳过的目录/文件（不覆盖用户数据）
            skip_dirs = {".venv", "__pycache__", "vector_db", "projects", "key", ".git", "_update_tmp"}
            skip_files = {".gitignore"}

            updated_count = 0
            for root, dirs, files in os.walk(source_dir):
                # 跳过特殊目录
                dirs[:] = [d for d in dirs if d not in skip_dirs]

                rel_root = os.path.relpath(root, source_dir)
                target_root = os.path.join(self.target_dir, rel_root) if rel_root != "." else self.target_dir
                os.makedirs(target_root, exist_ok=True)

                for fname in files:
                    if fname in skip_files:
                        continue
                    src = os.path.join(root, fname)
                    dst = os.path.join(target_root, fname)
                    shutil.copy2(src, dst)
                    updated_count += 1

            self.progress.emit(95, f"已更新 {updated_count} 个文件，正在清理…")

            # 清理临时文件
            shutil.rmtree(tmp_dir, ignore_errors=True)

            self.progress.emit(100, "更新完成！")
            self.finished.emit(True, f"成功更新 {updated_count} 个文件。请重启应用以生效。")

        except Exception as e:
            self.finished.emit(False, f"更新失败: {e}")
