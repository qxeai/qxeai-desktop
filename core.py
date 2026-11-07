import os
import re
import json
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Tuple

import jieba
from rapidfuzz import fuzz

jieba.setLogLevel(20)


@dataclass
class Entry:
    skill: str
    ask: str
    answer: str
    index: int


SKILL_RE = re.compile(r'^###\s*(.+?)\s*$')
ASK_RE = re.compile(r'^-\s*(\d+)\.\s*(.+?)\s*$')
_PUNCT = set('，。？！、；：""''（）【】《》,.!?;:()[]<>"\'')

SYNONYMS = {
    "如何": "怎么", "怎样": "怎么", "咋": "怎么", "咋样": "怎么", "咋办": "怎么",
    "为啥": "为什么", "什么原因": "为什么", "为何": "为什么",
    "啥": "什么", "何": "什么",
    "倒过来": "反转", "反过来": "反转", "颠倒": "反转", "翻转": "反转", "反向": "反转",
    "移除": "删除", "去掉": "删除", "删掉": "删除", "清除": "删除", "干掉": "删除",
    "新建": "创建", "建立": "创建", "生成": "创建", "做出": "创建", "建": "创建",
    "看看": "查看", "显示": "查看", "展示": "查看", "看一眼": "查看", "瞧瞧": "查看",
    "更改": "修改", "改动": "修改", "换成": "修改", "改一下": "修改", "调整": "修改",
    "报错": "错误", "异常": "错误", "出错": "错误", "bug": "错误", "问题": "错误",
    "变慢": "性能", "很慢": "性能", "卡顿": "性能", "速度慢": "性能", "慢": "性能",
    "电脑": "计算机", "pc": "计算机",
    "db": "数据库",
    "方法": "函数", "method": "函数", "function": "函数",
    "数组": "列表", "array": "列表", "list": "列表",
    "映射": "字典", "map": "字典", "dict": "字典",
    "装": "安装", "装上": "安装", "部署": "安装", "设置": "配置",
}

_PHRASES = sorted(
    [(k, v) for k, v in SYNONYMS.items() if len(k) > 1],
    key=lambda x: len(x[0]),
    reverse=True,
)


def normalize_text(s: str) -> str:
    s = s.lower()
    for k, v in _PHRASES:
        if k in s:
            s = s.replace(k, v)
    return s


def tokenize(s: str) -> set:
    s = normalize_text(s)
    en = set(re.findall(r'[a-z0-9_]+', s))
    zh = {t for t in jieba.cut(s)
          if t.strip() and t not in _PUNCT and not re.match(r'^[a-z0-9_]+$', t)}
    zh = {SYNONYMS.get(t, t) for t in zh}
    return en | zh


def parse_kb(text: str) -> List[Entry]:
    entries: List[Entry] = []
    state = {"skill": "未分类", "ask": None, "lines": [], "counter": 0}

    def flush():
        if state["ask"] is not None:
            state["counter"] += 1
            entries.append(Entry(
                skill=state["skill"],
                ask=state["ask"],
                answer="\n".join(state["lines"]).strip(),
                index=state["counter"],
            ))
        state["ask"] = None
        state["lines"] = []

    for raw in text.splitlines():
        line = raw.rstrip()
        m_skill = SKILL_RE.match(line)
        if m_skill:
            flush()
            state["skill"] = m_skill.group(1).strip()
            continue
        m_ask = ASK_RE.match(line)
        if m_ask:
            flush()
            state["ask"] = m_ask.group(2).strip()
            continue
        if state["ask"] is not None:
            if not state["lines"] and line.strip() == "":
                continue
            state["lines"].append(line)
    flush()
    return entries


def score(query: str, entry: Entry) -> float:
    q = query.strip().lower()
    a = entry.ask.strip().lower()
    if not q:
        return 0.0
    if q == a:
        return 100.0
    qn, an = normalize_text(q), normalize_text(a)
    if qn == an:
        return 95.0
    if qn in an or an in qn:
        return 88.0
    qt, at = tokenize(q), tokenize(a)
    if not qt or not at:
        return 0.0
    jac = len(qt & at) / len(qt | at)
    fuzzy = fuzz.token_set_ratio(qn, an) / 100.0
    return 60.0 * jac + 40.0 * fuzzy


def search(entries: List[Entry], query: str,
           top_k: int = 3, min_score: float = 20.0) -> List[Tuple[float, Entry]]:
    if not entries or not query.strip():
        return []
    scored = [(score(query, e), e) for e in entries]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(s, e) for s, e in scored[:top_k] if s >= min_score]


def save_entries(entries: List[Entry], path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(e) for e in entries], f, ensure_ascii=False, indent=2)


def load_entries(path: str) -> List[Entry]:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return [Entry(**d) for d in json.load(f)]
        except Exception:
            return []
    return []


def _checksum(entries: List[Entry]) -> str:
    payload = json.dumps([asdict(e) for e in entries],
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def export_mineai(entries: List[Entry], path: str) -> dict:
    meta = {
        "format": "mineai",
        "version": 1,
        "app": "MineAi",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(entries),
        "skills": sorted({e.skill for e in entries}),
        "checksum": _checksum(entries),
    }
    payload = dict(meta)
    payload["entries"] = [asdict(e) for e in entries]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return meta


def load_mineai(path: str) -> Tuple[List[Entry], dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or data.get("format") != "mineai":
        raise ValueError("不是有效的 .mineai 文件")
    ver = data.get("version", 0)
    if not isinstance(ver, int) or ver < 1:
        raise ValueError(f"不支持的版本：{ver}")
    if ver > 1:
        raise ValueError(f"该文件版本 {ver} 高于本程序支持的版本 1")
    raw = data.get("entries", [])
    if not isinstance(raw, list):
        raise ValueError("entries 字段损坏")
    entries = []
    for i, d in enumerate(raw, 1):
        if not isinstance(d, dict):
            continue
        entries.append(Entry(
            skill=str(d.get("skill", "未分类")),
            ask=str(d.get("ask", "")).strip(),
            answer=str(d.get("answer", "")),
            index=int(d.get("index", i)),
        ))
    entries = [e for e in entries if e.ask]
    for i, e in enumerate(entries, 1):
        e.index = i
    meta = {
        "format": "mineai",
        "version": ver,
        "app": data.get("app", "MineAi"),
        "exported_at": data.get("exported_at", ""),
        "count": len(entries),
        "skills": data.get("skills", []),
        "checksum_ok": _checksum(entries) == data.get("checksum"),
    }
    return entries, meta