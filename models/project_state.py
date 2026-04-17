# ============================================================
# models/project_state.py
# 项目状态管理：序列化/反序列化、保存/加载 .story.json、历史回退
# ============================================================

import json
import os
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional


@dataclass
class ProjectData:
    """
    整个项目的可序列化状态。
    对应存储到 .story.json 文件的完整数据结构。
    """
    # ----- 元信息 -----
    version: str = "1.0"
    created_at: str = ""
    updated_at: str = ""
    current_phase: str = "genesis"      # genesis | skeleton | flesh | locked
    current_node_index: int = 0         # Phase 3 当前处理到第几个节点

    # ----- Phase 1: 创世 -----
    sparkle: str = ""                                       # 一句话小说
    qa_pairs: List[dict] = field(default_factory=list)      # 苏格拉底盘问问答对
    world_variables: List[dict] = field(default_factory=list)   # 世界观变量
    finale_condition: str = ""                              # 终局条件
    story_title: str = ""                                   # 暂定标题

    # ----- Phase 1.5: 剧本结构配置 -----
    total_episodes: int = 20            # 总集数
    episode_duration: int = 3           # 每集时长（分钟）
    drama_style: str = "short_drama"    # "short_drama" | "traditional"
    story_genre: str = "custom"          # "crime" | "romance" | "suspense" | "revenge" | "fantasy" | "urban" | "comedy" | "custom"
    scenes_per_episode: str = "1-2"     # 默认每集场景数范围，如 "1-2" 或 "2-3"

    # ----- Phase 2: 骨架 -----
    cpg_title: str = ""
    cpg_nodes: List[dict] = field(default_factory=list)     # CPGNode 列表
    cpg_edges: List[dict] = field(default_factory=list)     # CausalEdge 列表
    hauge_stages: List[dict] = field(default_factory=list)  # Hauge 阶段数据

    # ----- Phase 2: 人物 -----
    characters: List[dict] = field(default_factory=list)           # Character 列表
    character_relations: List[dict] = field(default_factory=list)  # CharacterRelation 列表

    # ----- Phase 4: 血肉 -----
    confirmed_beats: Dict[str, Optional[dict]] = field(default_factory=dict)
    # { "Ep1": {...StoryBeat dict...}, "Ep2": null, ... }

    ite_results: Optional[dict] = None      # 最近一次 ITE 分析结果
    rag_results: Dict[str, dict] = field(default_factory=dict)

    # ----- Phase 5: 扩写 -----
    screenplay_texts: Dict[str, str] = field(default_factory=dict)  # {node_id: 剧本正文}
    # { "Ep1": {...RAG check result...}, ... }

    # ----- 操作历史（用于回退） -----
    generation_history: List[dict] = field(default_factory=list)
    # [{ "timestamp": "...", "action": "confirm_beat|generate_skeleton|...",
    #    "node": "Ep1", "snapshot": {...} }]

    def save_to_file(self, filepath: str) -> None:
        """保存项目到 .story.json 文件"""
        self.updated_at = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = self.updated_at

        data = asdict(self)

        # 确保目录存在
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load_from_file(cls, filepath: str) -> "ProjectData":
        """从 .story.json 文件加载项目"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(**data)

    def push_history(self, action: str, node_id: str = "", extra: dict = None):
        """
        记录一次操作到历史栈（用于回退）。
        action: confirm_beat | generate_skeleton | generate_variation | ...
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "node": node_id,
        }
        if extra:
            entry["extra"] = extra
        self.generation_history.append(entry)

    def get_confirmed_beat_count(self) -> int:
        """已确认的 Beat 数量"""
        return sum(1 for v in self.confirmed_beats.values() if v is not None)

    def get_total_node_count(self) -> int:
        """CPG 节点总数"""
        return len(self.cpg_nodes)

    def get_pending_nodes(self) -> List[dict]:
        """获取所有尚未确认 Beat 的节点"""
        confirmed_ids = {nid for nid, beat in self.confirmed_beats.items() if beat is not None}
        return [n for n in self.cpg_nodes if n.get("node_id") not in confirmed_ids]

    def reset_to_phase(self, phase: str):
        """
        回退到指定阶段，清除后续阶段的数据。
        用于"整体重新生成"场景。
        """
        if phase == "genesis":
            self.cpg_title = ""
            self.cpg_nodes = []
            self.cpg_edges = []
            self.hauge_stages = []
            self.confirmed_beats = {}
            self.ite_results = None
            self.rag_results = {}
            self.current_phase = "genesis"
        elif phase == "skeleton":
            self.confirmed_beats = {}
            self.ite_results = None
            self.rag_results = {}
            self.current_phase = "skeleton"
            self.current_node_index = 0
        elif phase == "flesh":
            self.current_phase = "flesh"
        # 记录回退操作
        self.push_history(f"reset_to_{phase}")


# ================================================================
# 节点版本管理工具函数
# ================================================================

def make_node_snapshot(node: dict) -> dict:
    """提取节点内容字段为版本快照"""
    result = {}
    for k in ("title", "setting", "emotional_tone", "episode_hook"):
        result[k] = node.get(k, "")
    for k in ("characters", "event_summaries"):
        v = node.get(k, [])
        result[k] = list(v) if isinstance(v, list) else []
    return result


def apply_snapshot(node: dict, snapshot: dict):
    """将版本快照应用到节点"""
    for k, v in snapshot.items():
        node[k] = list(v) if isinstance(v, list) else v


def add_version(node: dict, source: str, label: str = "") -> int:
    """
    为节点追加当前内容为新版本。
    source: ai_generate | manual | chat_refine | quick_regen | bvsr_rewrite | split | merge
    返回新版本的 ver_id。
    """
    from datetime import datetime
    if "versions" not in node:
        node["versions"] = []
    ver_id = len(node["versions"])
    node["versions"].append({
        "ver_id": ver_id,
        "source": source,
        "timestamp": datetime.now().isoformat(),
        "label": label or source,
        "snapshot": make_node_snapshot(node),
    })
    node["active_version"] = ver_id
    return ver_id


def get_active_version_snapshot(node: dict) -> dict:
    """获取当前激活版本的快照，若无版本就返回当前字段"""
    versions = node.get("versions", [])
    active_v = node.get("active_version", 0)
    if versions and active_v < len(versions):
        return versions[active_v]["snapshot"]
    return make_node_snapshot(node)


def update_version(node: dict, ver_idx: int = None):
    """
    覆盖保存：将节点当前内容更新到指定版本的 snapshot。
    ver_idx 为 None 时，更新 active_version。
    """
    from datetime import datetime
    versions = node.get("versions", [])
    if ver_idx is None:
        ver_idx = node.get("active_version", 0)
    if versions and 0 <= ver_idx < len(versions):
        versions[ver_idx]["snapshot"] = make_node_snapshot(node)
        versions[ver_idx]["timestamp"] = datetime.now().isoformat()


def set_active_version(node: dict, ver_idx: int):
    """设置激活版本并应用其快照"""
    versions = node.get("versions", [])
    if 0 <= ver_idx < len(versions):
        node["active_version"] = ver_idx
        apply_snapshot(node, versions[ver_idx]["snapshot"])

