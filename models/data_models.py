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
    """因果事件 — Story Beat 中的最小叙事单元"""
    event_id: int                       # 事件序号（Beat 内唯一）
    action: str                         # 事件描述
    causal_impact: str                  # 因果影响说明
    connects_to_previous: str = ""      # 与前序 Beat 的因果连接
    ite_score: float = -1.0             # ITE 分数（-1 表示尚未计算）
    ite_verdict: str = ""               # 关键 | 重要 | 普通 | 冗余
    is_pruned: bool = False             # 是否被 ITE 蒸馏剔除

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CausalEvent":
        return cls(**data)


@dataclass
class StoryBeat:
    """故事节拍 — 论文中的核心数据单元 (JSON Schema 对齐)"""
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

    def to_dict(self) -> dict:
        d = asdict(self)
        # causal_events 已经被 asdict 展开为 dict 列表
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "StoryBeat":
        events = [CausalEvent.from_dict(e) for e in data.get("causal_events", [])]
        data = dict(data)  # 浅拷贝
        data["causal_events"] = events
        return cls(**data)


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
    """CPG 图中的节点"""
    node_id: str                        # 如 "Ep1"
    title: str                          # 节点标题
    hauge_stage_id: int                 # Hauge 阶段 ID (1-6)
    setting: str = ""                   # 时空环境
    characters: List[str] = field(default_factory=list)
    event_summaries: List[str] = field(default_factory=list)  # 骨架中的事件摘要
    emotional_tone: str = ""            # 情感基调
    confirmed_beat: Optional[dict] = None   # 确认后的 StoryBeat (dict 形式)
    status: str = "pending"             # pending | in_progress | confirmed

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CPGNode":
        return cls(**data)

    @property
    def hauge_stage(self) -> HaugeStage:
        return HaugeStage.from_stage_id(self.hauge_stage_id)


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
    """角色 — 人物设定系统的核心数据单元"""
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
