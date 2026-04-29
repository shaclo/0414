# ============================================================
# models/data_models.py
# 核心数据结构：StoryBeat, CausalEvent, CPGNode, WorldVariable 等
# 所有模型均使用 dataclass，支持与 JSON 互转
# ============================================================

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from enum import Enum
import json


class HaugeStage(Enum):
    """Michael Hauge 六阶段叙事框架"""
    OPPORTUNITY = (1, "机会", "Opportunity")
    CHANGE_OF_PLANS = (2, "变点", "Change of Plans")
    POINT_OF_NO_RETURN = (3, "无路可退", "Point of No Return")
    MAJOR_SETBACK = (4, "主攻/挫折", "Major Setback")
    CLIMAX = (5, "高潮", "Climax")
    AFTERMATH = (6, "终局", "Aftermath")

    def __init__(self, stage_id, cn_name, en_name):
        self.stage_id = stage_id
        self.cn_name = cn_name
        self.en_name = en_name

    @property
    def display_name(self):
        """用于 UI 显示的名称，如 '机会 (Opportunity)'"""
        return f"{self.cn_name} ({self.en_name})"

    @classmethod
    def from_stage_id(cls, stage_id: int):
        """根据 stage_id 查找对应的枚举值"""
        for stage in cls:
            if stage.stage_id == stage_id:
                return stage
        raise ValueError(f"未知的 Hauge 阶段 ID: {stage_id}")


@dataclass
class CausalEvent:
    """因果事件 — Story Beat 中的最小叙事单元（v1.1.6 升级）。

    v1.1.6 新增字段：
        twist_type     — none | 反转 | 信息突破 | 立场翻转 | 秘密暴露
        tau_estimate   — AI 自评因果贡献度（0~1，要求 ≥0.1，<0.05 视为水分）
    """
    event_id: int                       # 事件序号（Beat 内唯一）
    action: str                         # 事件描述
    causal_impact: str                  # 因果影响说明
    connects_to_previous: str = ""      # 与前序 Beat 的因果连接
    ite_score: float = -1.0             # ITE 分数（-1 表示尚未计算）
    ite_verdict: str = ""               # 关键 | 重要 | 普通 | 冗余
    is_pruned: bool = False             # 是否被 ITE 蒸馏剔除
    # v1.1.6 新增字段
    twist_type: str = "none"            # none | 反转 | 信息突破 | 立场翻转 | 秘密暴露
    tau_estimate: float = -1.0          # AI 自评 τ 值（要求 ≥0.1）
    serves_core_conflict: str = ""      # 该事件如何服务于核心冲突

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CausalEvent":
        valid = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid}
        return cls(**filtered)


@dataclass
class StoryBeat:
    """故事节拍 — 论文中的核心数据单元（v1.1.6 升级 JSON Schema）。

    v1.1.6 新增 4 个字段（输出验收硬指标）：
        character_micro_change — 本集 A 级角色的微变化点（动作/台词外化，禁止内心独白）
        twist_summary          — 本集 ≥1 处转折点的简述（与 causal_events.twist_type 配合使用）
        cp_interaction_used    — 本集采用的 CP 互动模板（仅 has_cp_main_line=True 时填写）
                                  格式：{"id": "genre_004", "rendered_text": "..."}
        density_score          — 自评因果事件密度（int，要求 ≥3）
    """
    beat_id: int                        # 全局唯一 ID
    target_node_id: str                 # 所属 CPG 节点 ID
    persona_name: str                   # 生成该 Beat 的人格名称
    setting: str                        # 时空环境描述
    entities: List[str]                 # 活跃角色/物品
    causal_events: List[CausalEvent]    # 因果事件列表
    hook: str                           # 悬念钩子
    rationale: str = ""                 # 人格创作理由
    is_selected: bool = False           # 是否被用户选中
    user_edited: bool = False           # 是否被用户手动修改过
    # v1.1.6 新增字段
    character_micro_change: str = ""    # 本集 A 级角色的微变化点
    twist_summary: str = ""             # 本集转折点简述
    cp_interaction_used: Optional[dict] = None
    # 例：{"id": "genre_004", "rendered_text": "...", "hook_type": "反转钩"}
    density_score: int = 0              # 自评密度分（≥3 为合格）

    def to_dict(self) -> dict:
        d = asdict(self)
        # causal_events 已经被 asdict 展开为 dict 列表
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "StoryBeat":
        events = [CausalEvent.from_dict(e) for e in data.get("causal_events", [])]
        data = dict(data)  # 浅拷贝
        data["causal_events"] = events
        # 兼容旧存档：过滤未知字段，缺失字段使用默认值
        valid = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid}
        return cls(**filtered)


@dataclass
class WorldVariable:
    """世界观变量 — 真理锚点"""
    var_id: str                         # 如 "var_001"
    category: str                       # 世界规则 | 角色设定 | 道具能力 | 社会制度 | 终局条件
    name: str                           # 变量名称
    definition: str                     # 精确定义
    constraints: str                    # 限制/例外条件

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "WorldVariable":
        return cls(**data)


@dataclass
class QAPair:
    """苏格拉底盘问的问答对"""
    question_id: int
    dimension: str                      # 追问维度
    question: str                       # 问题内容
    rationale: str                      # 追问理由
    answer: str = ""                    # 用户回答

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "QAPair":
        return cls(**data)


@dataclass
class CPGNode:
    """
    CPG 图中的节点 (v1.1.6 颗粒度升级)。

    设计思路（v1.1.6 hybrid 方案）：
        - **node_id 仍为集级别**（"Ep1"/"Ep2"...），保证下游 confirmed_beats /
          screenplay_texts / hook_selections / RAG 索引兼容旧版本。
        - **节点内部新增 event_units 字段**，承载事件级因果颗粒（每集 2-4 个独立因果事件，
          每个事件可独立成戏，禁止动作切片堆叠）。这是真正解决"7 集打 1 个怪"密度问题的关键。
        - 旧字段 event_summaries（List[str]）保留向后兼容；新存档由 worker 自动从
          event_units 同步生成 event_summaries。
        - main_scene 用于"同一主场景最多跨 2 集"约束。

    示例 event_unit:
        {
          "unit_id": "Ep1-A",
          "action": "林夏发现石台符文藏家族徽记",
          "twist_type": "信息突破",
          "tau_estimate": 0.35,
          "causal_impact": "为反派身份揭露铺垫"
        }
    """
    node_id: str                        # 集级 ID，如 "Ep1"
    title: str                          # 节点标题
    hauge_stage_id: int                 # Hauge 阶段 ID (1-6)
    setting: str = ""                   # 时空环境
    characters: List[str] = field(default_factory=list)
    event_summaries: List[str] = field(default_factory=list)  # 旧字段：纯字符串事件摘要
    emotional_tone: str = ""            # 情感基调
    confirmed_beat: Optional[dict] = None   # 确认后的 StoryBeat (dict 形式)
    status: str = "pending"             # pending | in_progress | confirmed
    # ---- v1.1.6 新增字段 ----
    event_units: List[dict] = field(default_factory=list)
    # 事件级因果单元列表（每集 2-4 个）；为空时表示节点尚未升级到 v1.1.6 schema
    main_scene: str = ""                # 本集主场景（如 "古殿深处"），用于场景多样性校验
    episode_hook: str = ""              # 本集结尾钩子（旧版本可能放在其他位置，此处统一）
    opening_hook: str = ""              # 本集开篇承接（同上）

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CPGNode":
        # 兼容旧存档：过滤未知字段，缺失字段使用默认值
        valid_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    @property
    def hauge_stage(self) -> HaugeStage:
        return HaugeStage.from_stage_id(self.hauge_stage_id)

    @property
    def episode_id(self) -> str:
        """v1.1.6 hybrid 方案下，node_id 即 episode_id。保留方法是为了 UI 兼容。"""
        return self.node_id or ""

    @property
    def has_event_units(self) -> bool:
        """是否已升级到 v1.1.6 schema（带事件级因果单元）。"""
        return bool(self.event_units)

    @property
    def density_score(self) -> int:
        """因果事件密度（v1.1.6 验收指标 A1）。"""
        return len(self.event_units) if self.event_units else len(self.event_summaries)


@dataclass
class EventUnit:
    """
    事件级因果单元 (v1.1.6 新增)。
    一集内的最小独立因果单元，每集 2-4 个，每个都能独立成戏。
    """
    unit_id: str                        # 如 "Ep1-A"
    action: str                         # 事件描述
    twist_type: str = "none"            # none | 反转 | 信息突破 | 立场翻转 | 秘密暴露
    tau_estimate: float = -1.0          # AI 自评因果贡献度（要求 ≥0.1，<0.05 视为冗余）
    causal_impact: str = ""             # 因果影响（推动后续什么剧情）
    is_pruned: bool = False             # ITE 裁剪标记

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EventUnit":
        valid_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class CausalEdge:
    """CPG 图中的因果边"""
    from_node: str                      # 起始节点 ID
    to_node: str                        # 目标节点 ID
    causal_type: str                    # 直接因果 | 间接影响 | 情感驱动
    description: str                    # 因果描述

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CausalEdge":
        return cls(**data)


@dataclass
class HaugeStageData:
    """Hauge 阶段数据（骨架生成时使用）"""
    stage_id: int
    stage_name: str
    stage_description: str
    nodes: List[CPGNode] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "stage_id": self.stage_id,
            "stage_name": self.stage_name,
            "stage_description": self.stage_description,
            "nodes": [n.to_dict() for n in self.nodes],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HaugeStageData":
        nodes = [CPGNode.from_dict(n) for n in data.get("nodes", [])]
        return cls(
            stage_id=data["stage_id"],
            stage_name=data["stage_name"],
            stage_description=data["stage_description"],
            nodes=nodes,
        )


@dataclass
class Character:
    """
    角色 — 人物设定系统的核心数据单元（v1.1.6 升级）。

    v1.1.6 新增字段（用于"极致人设"叙事策略）：
        signature_traits   — 标签化爆点列表（最多 3 个，A 级角色必填 3 个）
                             例：阿肆 = ["呆萌傲娇", "深情隐忍", "战力爆表"]
        arc_outline        — 粗弧线描述
                             例：林夏 = "惊恐 → 接受非人化 → 主宰"
        cp_role            — CP 主角色标记（"A" / "B" / ""）
                             用于血肉阶段从 cp_interaction_templates.json 抽样时
                             识别 {role_a} / {role_b} 占位符的注入对象
    """
    char_id: str                        # 如 "char_001"
    name: str                           # 角色姓名
    role_type: str = "配角"             # 主角 | 反派 | 辅助 | 配角 | 群演
    gender: str = "未知"                # 男 | 女 | 其他 | 未知
    age: str = ""                       # 年龄，可以是数字或描述如"中年"
    position: str = ""                  # 职位/身份，如"宫廷侍卫长"
    personality: str = ""               # 性格特征，如"机敏、隐忍、内心矛盾"
    motivation: str = ""                # 核心动机（最想达成什么）
    appearance: str = ""                # 关键外貌特征
    notes: str = ""                     # 备注（自由文本）
    importance_level: str = "C"         # A | B | C（角色重要性等级）
    # v1.1.6 新增字段
    signature_traits: List[str] = field(default_factory=list)  # 最多 3 个标签化爆点
    arc_outline: str = ""               # 粗弧线描述
    cp_role: str = ""                   # CP 角色：A | B | ""（仅在 has_cp_main_line=True 时有意义）

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Character":
        valid_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    def to_prompt_summary(self) -> str:
        """生成供 AI 使用的角色简述（注入到 Prompt 中）"""
        parts = [f"【{self.role_type}】{self.name}"]
        if self.position:
            parts.append(f"身份:{self.position}")
        if self.personality:
            parts.append(f"性格:{self.personality}")
        if self.motivation:
            parts.append(f"动机:{self.motivation}")
        if self.appearance:
            parts.append(f"外貌:{self.appearance}")
        if self.signature_traits:
            parts.append(f"极致人设:{ '+'.join(self.signature_traits) }")
        if self.arc_outline:
            parts.append(f"弧线:{self.arc_outline}")
        return "  ".join(parts)


@dataclass
class CharacterRelation:
    """人物关系"""
    from_char_id: str                   # 起始角色 ID
    to_char_id: str                     # 目标角色 ID
    relation_type: str                  # 如"父子/敌对"、"主从/信任"
    description: str = ""              # 关系补充说明

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterRelation":
        valid_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)
