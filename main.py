import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from core import (
    parse_kb, search, save_entries, load_entries,
    export_mineai, load_mineai,
)

APP_NAME = "QXEAi"
MODEL_EXTS = (".qxeai", ".mineai")
EXAMPLE = """### Python 基础
-1.什么是列表推导式？
列表推导式是 Python 中创建列表的简洁语法。
-2.如何反转一个列表？
使用切片 lst[::-1] 返回新列表，或调用 lst.reverse() 原地反转。

### 数据库
-1.什么是索引？
索引是加速查询的数据结构。
"""


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def writable_dir(preferred):
    try:
        os.makedirs(preferred, exist_ok=True)
        probe = os.path.join(preferred, ".qxeai_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return preferred
    except Exception:
        if sys.platform == "win32":
            base = os.environ.get("APPDATA", os.path.expanduser("~"))
        elif sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support")
        else:
            base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        d = os.path.join(base, "QXEAi")
        os.makedirs(d, exist_ok=True)
        return d


DATA_DIR = writable_dir(app_dir())
KB_PATH = os.path.join(DATA_DIR, "qxeai_kb.json")


class QXEAiApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1060x780")
        self.entries = load_entries(KB_PATH)
        self.status_var = tk.StringVar()
        self.path_var = tk.StringVar(value=f"数据文件：{KB_PATH}")
        self.replace_var = tk.BooleanVar(value=False)
        self.query_var = tk.StringVar()
        self.topk_var = tk.IntVar(value=3)
        self.min_var = tk.IntVar(value=20)
        self.kb_count_var = tk.StringVar()
        self._build()
        self._refresh_status()
        self._refresh_kb_view()

    def _build(self):
        top = ttk.Frame(self.root, padding=(12, 8))
        top.pack(fill="x")
        ttk.Label(top, text=APP_NAME, font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Label(top, textvariable=self.status_var).pack(side="right")
        ttk.Label(self.root, textvariable=self.path_var, foreground="#666").pack(fill="x", padx=12)

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        self._build_import_tab(nb)
        self._build_search_tab(nb)
        self._build_kb_tab(nb)

    def _build_import_tab(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="导入知识库")

        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="打开文件", command=self._pick_file).pack(side="left")
        ttk.Checkbutton(bar, text="清空后导入", variable=self.replace_var).pack(side="left", padx=8)
        ttk.Button(bar, text="解析上方文本并导入", command=self._import_text).pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(bar, text="导出 .qxeai", command=self._export_model).pack(side="left")

        self.text_edit = ScrolledText(frame, wrap="word", font=("Consolas", 10))
        self.text_edit.pack(fill="both", expand=True)
        self.text_edit.insert("end", EXAMPLE)

    def _build_search_tab(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="检索问答")

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text="问题：").pack(side="left")
        entry = ttk.Entry(row, textvariable=self.query_var)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        entry.bind("<Return>", lambda e: self._search())
        ttk.Button(row, text="搜索", command=self._search).pack(side="left")

        row2 = ttk.Frame(frame)
        row2.pack(fill="x", pady=(0, 8))
        ttk.Label(row2, text="Top-K：").pack(side="left")
        ttk.Spinbox(row2, from_=1, to=20, textvariable=self.topk_var, width=6).pack(side="left", padx=(0, 12))
        ttk.Label(row2, text="最低相关度：").pack(side="left")
        ttk.Spinbox(row2, from_=0, to=100, textvariable=self.min_var, width=6).pack(side="left", padx=(0, 12))
        ttk.Button(row2, text="清空结果", command=lambda: self._set_result("")).pack(side="left")

        self.result_view = ScrolledText(frame, wrap="word", font=("Consolas", 10), state="disabled")
        self.result_view.pack(fill="both", expand=True)
        self.result_view.tag_configure("title", font=("Consolas", 10, "bold"))

    def _build_kb_tab(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text="知识库")

        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="刷新", command=self._reload_from_disk).pack(side="left")
        ttk.Button(bar, text="清空知识库", command=self._clear_kb).pack(side="left", padx=8)
        ttk.Label(bar, textvariable=self.kb_count_var).pack(side="right")

        self.kb_view = ScrolledText(frame, wrap="word", font=("Consolas", 9), state="disabled")
        self.kb_view.pack(fill="both", expand=True)

    def _reload_from_disk(self):
        self.entries = load_entries(KB_PATH)
        self._refresh_status()
        self._refresh_kb_view()

    def _clear_kb(self):
        if not self.entries:
            return
        if not messagebox.askyesno("确认", f"确定清空全部 {len(self.entries)} 条？"):
            return
        self.entries = []
        try:
            save_entries(self.entries, KB_PATH)
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            return
        self._refresh_status()
        self._refresh_kb_view()
        messagebox.showinfo("完成", "已清空")

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="选择知识库文件",
            filetypes=[
                ("QXEAi / 文本", "*.qxeai *.mineai *.md *.markdown *.txt"),
                ("QXEAi 模型", "*.qxeai *.mineai"),
                ("文本", "*.md *.markdown *.txt"),
                ("所有", "*.*"),
            ],
        )
        if not path:
            return

        if path.lower().endswith(MODEL_EXTS):
            try:
                new_entries, meta = load_mineai(path)
            except Exception as e:
                messagebox.showerror("读取 .qxeai 失败", str(e))
                return
            if not new_entries:
                messagebox.showwarning("提示", ".qxeai 中没有可用条目")
                return
            if not meta.get("checksum_ok", True):
                if not messagebox.askyesno("校验警告", "校验和不一致，仍要导入？"):
                    return
            self._merge_entries(new_entries, label=f".qxeai（{os.path.basename(path)}）")
            return

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return

        self.text_edit.delete("1.0", "end")
        self.text_edit.insert("end", content)

        new = parse_kb(content)
        if not new:
            messagebox.showwarning(
                "未解析到条目",
                "文件内容未匹配到格式。\n\n"
                "需包含：\n  ### 技能名\n  -1.问题\n  答案\n\n"
                "请检查是否有前导空格，或答案中是否混入了 -数字. 开头的行。",
            )
            return
        self._merge_entries(new, label=f"文本（{os.path.basename(path)}）")

    def _import_text(self):
        content = self.text_edit.get("1.0", "end")
        if not content.strip():
            messagebox.showwarning("提示", "内容为空")
            return
        new = parse_kb(content)
        if not new:
            messagebox.showwarning("提示", "未解析到条目，请检查格式")
            return
        self._merge_entries(new, label="粘贴文本")

    def _merge_entries(self, new_entries, label=""):
        if self.replace_var.get():
            self.entries = []

        existing = {e.ask.strip().lower() for e in self.entries}
        added = skipped = 0
        for e in new_entries:
            k = e.ask.strip().lower()
            if not k:
                continue
            if k not in existing:
                self.entries.append(e)
                existing.add(k)
                added += 1
            else:
                skipped += 1

        for i, e in enumerate(self.entries, 1):
            e.index = i

        save_error = None
        disk_count = -1
        try:
            save_entries(self.entries, KB_PATH)
            disk_count = len(load_entries(KB_PATH))
        except Exception as ex:
            save_error = str(ex)

        self._refresh_status()
        self._refresh_kb_view()

        summary = (
            f"来源：{label or '未知'}\n"
            f"解析：{len(new_entries)} 条\n"
            f"新增：{added} 条\n"
            f"跳过重复：{skipped} 条\n"
            f"当前总数：{len(self.entries)} 条\n"
            f"文件：{KB_PATH}"
        )

        if save_error:
            messagebox.showerror("保存失败", f"{save_error}\n\n{summary}")
            return
        if disk_count != len(self.entries):
            messagebox.showerror(
                "保存校验失败",
                f"内存 {len(self.entries)} 条，磁盘 {disk_count} 条\n\n{summary}",
            )
            return
        if added == 0:
            messagebox.showwarning(
                "未新增",
                f"{summary}\n\n"
                "所有条目均与现有知识库重复。\n"
                "如需替换：勾选「清空后导入」再试；\n"
                "如需追加：换一份不同的知识库。",
            )
            return
        messagebox.showinfo("导入完成", summary)

    def _export_model(self):
        if not self.entries:
            messagebox.showwarning("提示", "知识库为空，无可导出内容")
            return
        path = filedialog.asksaveasfilename(
            title="导出 .qxeai 模型",
            defaultextension=".qxeai",
            initialfile="qxeai_model.qxeai",
            filetypes=[("QXEAi 模型", "*.qxeai"), ("所有", "*.*")],
        )
        if not path:
            return
        try:
            meta = export_mineai(self.entries, path)
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
            return
        size_kb = os.path.getsize(path) / 1024
        messagebox.showinfo(
            "导出完成",
            f"条目：{meta['count']} 条\n技能组：{len(meta['skills'])} 个\n"
            f"文件大小：{size_kb:.1f} KB\n路径：{path}",
        )

    def _search(self):
        q = self.query_var.get().strip()
        if not q:
            return
        if not self.entries:
            self._set_result("知识库为空，请先到「导入知识库」页导入内容。")
            return
        results = search(self.entries, q,
                         top_k=self.topk_var.get(),
                         min_score=float(self.min_var.get()))
        if not results:
            self._set_result(
                f"未找到匹配项。\n"
                f"当前知识库：{len(self.entries)} 条\n"
                f"当前阈值：{self.min_var.get()}\n\n"
                f"建议：\n"
                f"  1. 降低阈值到 0 再搜一次\n"
                f"  2. 到「知识库」页确认条目确实存在\n"
                f"  3. 换个更接近知识库问题的说法"
            )
            return
        self.result_view.configure(state="normal")
        self.result_view.delete("1.0", "end")
        for rank, (s, e) in enumerate(results, 1):
            tag = "最佳答案" if rank == 1 else f"#{rank} 备选"
            self.result_view.insert("end", f"[{tag}]  相关度 {s:.1f}\n", "title")
            self.result_view.insert("end", f"技能组：{e.skill}\n")
            self.result_view.insert("end", f"问题：{e.ask}\n")
            self.result_view.insert("end", f"答案：\n{e.answer}\n")
            self.result_view.insert("end", "\n" + "-" * 60 + "\n\n")
        self.result_view.configure(state="disabled")

    def _set_result(self, s):
        self.result_view.configure(state="normal")
        self.result_view.delete("1.0", "end")
        if s:
            self.result_view.insert("end", s)
        self.result_view.configure(state="disabled")

    def _refresh_status(self):
        if not self.entries:
            self.status_var.set("知识库：空")
            return
        skills = sorted({e.skill for e in self.entries})
        self.status_var.set(f"知识库：{len(self.entries)} 条 / {len(skills)} 技能组")

    def _refresh_kb_view(self):
        if hasattr(self, "kb_count_var"):
            self.kb_count_var.set(f"共 {len(self.entries)} 条")
        if not hasattr(self, "kb_view"):
            return
        self.kb_view.configure(state="normal")
        self.kb_view.delete("1.0", "end")
        if not self.entries:
            self.kb_view.insert("end", "（空）")
        else:
            cur = None
            for e in self.entries:
                if e.skill != cur:
                    cur = e.skill
                    self.kb_view.insert("end", f"\n### {e.skill}\n")
                self.kb_view.insert("end", f"-{e.index}. {e.ask}\n")
                if e.answer:
                    self.kb_view.insert("end", f"{e.answer}\n")
        self.kb_view.configure(state="disabled")


def main():
    root = tk.Tk()
    QXEAiApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
