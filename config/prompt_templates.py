# ============================================================
# config/prompt_templates.py
# 爽感公式 & 钩子公式 管理器
# 支持 JSON 持久化 + 随机抽样注入
# ============================================================

import json
import os
import random
from dataclasses import dataclass, field, asdict
from typing import List, Optional

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
_TEMPLATES_FILE = os.path.join(_CONFIG_DIR, "prompt_templates.json")


@dataclass
class SatisfactionTemplate:
    id: str
    name: str
    level: str          # "small" | "medium" | "big"
    prompt_text: str
    enabled: bool = True


@dataclass
class HookTemplate:
    id: str
    name: str
    prompt_text: str
    enabled: bool = True


class PromptTemplateManager:
    """管理爽感和钩子模板，支持 JSON 持久化 + 随机抽样"""

    def __init__(self):
        self._satisfactions: List[SatisfactionTemplate] = []
        self._hooks: List[HookTemplate] = []
        self.load()

    # ---- 持久化 ----
    def load(self):
        if os.path.exists(_TEMPLATES_FILE):
            with open(_TEMPLATES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._satisfactions = [SatisfactionTemplate(**s) for s in data.get("satisfactions", [])]
            self._hooks = [HookTemplate(**h) for h in data.get("hooks", [])]
        else:
            self._load_defaults()
            self.save()

    def save(self):
        data = {
            "satisfactions": [asdict(s) for s in self._satisfactions],
            "hooks": [asdict(h) for h in self._hooks],
        }
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        with open(_TEMPLATES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---- 爽感 CRUD ----
    def get_satisfactions(self) -> List[SatisfactionTemplate]:
        return self._satisfactions

    def add_satisfaction(self, t: SatisfactionTemplate):
        self._satisfactions.append(t)
        self.save()

    def update_satisfaction(self, idx: int, t: SatisfactionTemplate):
        self._satisfactions[idx] = t
        self.save()

    def remove_satisfaction(self, idx: int):
        self._satisfactions.pop(idx)
        self.save()

    def toggle_satisfaction(self, idx: int, enabled: bool):
        self._satisfactions[idx].enabled = enabled
        self.save()

    # ---- 钩子 CRUD ----
    def get_hooks(self) -> List[HookTemplate]:
        return self._hooks

    def add_hook(self, t: HookTemplate):
        self._hooks.append(t)
        self.save()

    def update_hook(self, idx: int, t: HookTemplate):
        self._hooks[idx] = t
        self.save()

    def remove_hook(self, idx: int):
        self._hooks.pop(idx)
        self.save()

    def toggle_hook(self, idx: int, enabled: bool):
        self._hooks[idx].enabled = enabled
        self.save()

    # ---- 随机抽样 ----
    def sample_satisfaction_prompt(self, n: int = 3) -> str:
        pool = [s for s in self._satisfactions if s.enabled]
        if not pool:
            return ""
        chosen = random.sample(pool, min(n, len(pool)))
        parts = []
        for i, s in enumerate(chosen, 1):
            level_cn = {"small": "小爽", "medium": "中爽", "big": "大爽"}.get(s.level, s.level)
            parts.append(f"**候选{i}: {s.name}（{level_cn}）**\n{s.prompt_text}")
        n_chosen = len(chosen)
        header = (
            '## 爽感节奏设计（必须严格遵守！）\n'
            '- 每集必须有至少 1 个「小爽点」\n'
            '- 每 3 集必须安排 1 个「中爽点」\n'
            '- 每 10 集必须安排 1 个「大爽点」\n\n'
            f'### 以下是 {n_chosen} 种爽感公式候选，请选择最适合本集剧情、'
            '最能制造反差和观众满足感的 1 种来写：\n\n'
        )
        return header + "\n\n".join(parts)
    def sample_hook_prompt(self, n: int = 2) -> str:
        pool = [h for h in self._hooks if h.enabled]
        if not pool:
            return ""
        chosen = random.sample(pool, min(n, len(pool)))
        parts = []
        for i, h in enumerate(chosen, 1):
            parts.append(f"**候选{i}: {h.name}**\n{h.prompt_text}")
        n_chosen = len(chosen)
        header = (
            f'## 本集钩子公式候选（配合上述钩子写作铁律使用）\n'
            f'请从以下 {n_chosen} 种钩子公式中选择最适合本集剧情的 **1 种**，\n'
            f'按照公式的格式和写法要求严格执行：\n\n'
        )
        footer = (
            '\n\n### 自检：写完最后 3 行后问自己\n'
            '1. 如果我是观众，看到这里会不会立刻想滑到下一集？\n'
            '2. 这个钩子是「正在发生的动作被中断」还是「已经结束的事情被描述」？\n'
            '3. 钩子中是否包含了具体的角色名+具体动作？'
        )
        return header + "\n\n".join(parts) + footer

    # ---- 按 ID 列表构建（供 UI 多选使用） ----
    def build_satisfaction_prompt_by_ids(self, ids: List[str]) -> str:
        chosen = [s for s in self._satisfactions if s.id in ids]
        if not chosen:
            return ""
        parts = []
        for i, s in enumerate(chosen, 1):
            level_cn = {"small": "\u5c0f\u723d", "medium": "\u4e2d\u723d", "big": "\u5927\u723d"}.get(s.level, s.level)
            parts.append(f"**\u5019\u9009{i}: {s.name}\uff08{level_cn}\uff09**\n{s.prompt_text}")
        n_chosen = len(chosen)
        header = (
            '## \u723d\u611f\u8282\u594f\u8bbe\u8ba1\uff08\u5fc5\u987b\u4e25\u683c\u9075\u5b88\uff01\uff09\n'
            '- \u6bcf\u96c6\u5fc5\u987b\u6709\u81f3\u5c11 1 \u4e2a\u300c\u5c0f\u723d\u70b9\u300d\n'
            '- \u6bcf 3 \u96c6\u5fc5\u987b\u5b89\u6392 1 \u4e2a\u300c\u4e2d\u723d\u70b9\u300d\n'
            '- \u6bcf 10 \u96c6\u5fc5\u987b\u5b89\u6392 1 \u4e2a\u300c\u5927\u723d\u70b9\u300d\n\n'
            f'### \u4ee5\u4e0b\u662f {n_chosen} \u79cd\u723d\u611f\u516c\u5f0f\u5019\u9009\uff0c\u8bf7\u9009\u62e9\u6700\u9002\u5408\u672c\u96c6\u5267\u60c5\u3001'
            '\u6700\u80fd\u5236\u9020\u53cd\u5dee\u548c\u89c2\u4f17\u6ee1\u8db3\u611f\u7684 1 \u79cd\u6765\u5199\uff1a\n\n'
        )
        return header + "\n\n".join(parts)

    def build_hook_prompt_by_ids(self, ids: List[str]) -> str:
        chosen = [h for h in self._hooks if h.id in ids]
        if not chosen:
            return ""
        parts = []
        for i, h in enumerate(chosen, 1):
            parts.append(f"**\u5019\u9009{i}: {h.name}**\n{h.prompt_text}")
        n_chosen = len(chosen)
        header = (
            f'## \u672c\u96c6\u94a9\u5b50\u516c\u5f0f\u5019\u9009\uff08\u914d\u5408\u4e0a\u8ff0\u94a9\u5b50\u5199\u4f5c\u94c1\u5f8b\u4f7f\u7528\uff09\n'
            f'\u8bf7\u4ece\u4ee5\u4e0b {n_chosen} \u79cd\u94a9\u5b50\u516c\u5f0f\u4e2d\u9009\u62e9\u6700\u9002\u5408\u672c\u96c6\u5267\u60c5\u7684 **1 \u79cd**\uff0c\n'
            f'\u6309\u7167\u516c\u5f0f\u7684\u683c\u5f0f\u548c\u5199\u6cd5\u8981\u6c42\u4e25\u683c\u6267\u884c\uff1a\n\n'
        )
        footer = (
            '\n\n### \u81ea\u68c0\uff1a\u5199\u5b8c\u6700\u540e 3 \u884c\u540e\u95ee\u81ea\u5df1\n'
            '1. \u5982\u679c\u6211\u662f\u89c2\u4f17\uff0c\u770b\u5230\u8fd9\u91cc\u4f1a\u4e0d\u4f1a\u7acb\u523b\u60f3\u6ed1\u5230\u4e0b\u4e00\u96c6\uff1f\n'
            '2. \u8fd9\u4e2a\u94a9\u5b50\u662f\u300c\u6b63\u5728\u53d1\u751f\u7684\u52a8\u4f5c\u88ab\u4e2d\u65ad\u300d\u8fd8\u662f\u300c\u5df2\u7ecf\u7ed3\u675f\u7684\u4e8b\u60c5\u88ab\u63cf\u8ff0\u300d\uff1f\n'
            '3. \u94a9\u5b50\u4e2d\u662f\u5426\u5305\u542b\u4e86\u5177\u4f53\u7684\u89d2\u8272\u540d+\u5177\u4f53\u52a8\u4f5c\uff1f'
        )
        return header + "\n\n".join(parts) + footer

    # ---- 按集号调度爽感等级 ----
    def determine_satisfaction_level(self, episode_number: int,
                                     small_interval: int = 1,
                                     medium_interval: int = 3,
                                     big_interval: int = 10) -> str:
        """
        根据集号确定本集应该包含的爽感等级。
        返回 'big' / 'medium' / 'small'。
        大爽优先级 > 中爽 > 小爽
        """
        if big_interval > 0 and episode_number % big_interval == 0:
            return "big"
        if medium_interval > 0 and episode_number % medium_interval == 0:
            return "medium"
        return "small"

    def build_satisfaction_prompt_for_episode(
        self,
        episode_number: int,
        required_level: str,
        selected_ids: List[str] = None,
        sample_count: int = 3,
    ) -> str:
        """
        为指定集号生成爽感 prompt，明确告知 AI 本集需要哪个等级的爽感。
        - selected_ids: 用户勾选的公式 ID 列表（优先）
        - 如果未勾选，则从对应等级的启用公式中随机抽取
        """
        level_cn = {"small": "\u5c0f\u723d", "medium": "\u4e2d\u723d", "big": "\u5927\u723d"}.get(required_level, required_level)

        # 筛选候选公式
        if selected_ids:
            # 用户勾选：优先用对应等级，不够则用全部勾选
            chosen = [s for s in self._satisfactions if s.id in selected_ids and s.level == required_level]
            if not chosen:
                chosen = [s for s in self._satisfactions if s.id in selected_ids]
        else:
            # 未勾选：从启用的对应等级中随机抽取
            pool = [s for s in self._satisfactions if s.enabled and s.level == required_level]
            if not pool:
                pool = [s for s in self._satisfactions if s.enabled]
            chosen = random.sample(pool, min(sample_count, len(pool))) if pool else []

        if not chosen:
            return ""

        parts = []
        for i, s in enumerate(chosen, 1):
            s_level_cn = {"small": "\u5c0f\u723d", "medium": "\u4e2d\u723d", "big": "\u5927\u723d"}.get(s.level, s.level)
            parts.append(f"**\u5019\u9009{i}: {s.name}\uff08{s_level_cn}\uff09**\n{s.prompt_text}")

        n_chosen = len(chosen)
        header = (
            f'## \u723d\u611f\u8282\u594f\u8bbe\u8ba1\uff08\u672c\u96c6\u5fc5\u987b\u4e25\u683c\u9075\u5b88\uff01\uff09\n'
            f'\u672c\u96c6\u4e3a\u7b2c {episode_number} \u96c6\u3002\u6839\u636e\u6574\u4f53\u8282\u594f\u89c4\u5212\uff0c'
            f'**\u672c\u96c6\u5fc5\u987b\u5305\u542b\u4e00\u4e2a\u300c{level_cn}\u300d\u7ea7\u522b\u7684\u723d\u611f\u9ad8\u6f6e**\u3002\n\n'
            f'### \u4ee5\u4e0b\u662f {n_chosen} \u79cd\u300c{level_cn}\u300d\u516c\u5f0f\u5019\u9009\uff0c'
            f'\u8bf7\u9009\u62e9\u6700\u9002\u5408\u672c\u96c6\u5267\u60c5\u7684 1 \u79cd\u6765\u5199\uff1a\n\n'
        )
        return header + "\n\n".join(parts)


    # ---- 默认模板 ----
    def _load_defaults(self):
        self._satisfactions = [
            SatisfactionTemplate(
                id="face_slap", name="打脸反杀", level="small",
                prompt_text=(
                    "**情绪弧线**: 屈辱压抑 → 愤怒积蓄 → 爆发释放 → 全场震惊\n"
                    "**四步行文**:\n"
                    "  第1步「铺垫屈辱」: 对手必须当众用最恶毒的语言/行为羞辱主角\n"
                    "    - 写出具体的嘲讽台词，周围人的嘲笑反应要写出来\n"
                    "  第2步「觉醒征兆」: 用 2-3 行写主角内在力量苏醒的物理表现\n"
                    "    - ✅ \"她低着头，凌乱的长发遮住了脸。体内一股冰冷锐利的力量在疯狂奔涌\"\n"
                    "    - ❌ \"她突然变强了\"（太抽象）\n"
                    "  第3步「碾压反击」: 反击必须压倒性，一招制敌，不能拖泥带水\n"
                    "    - 用具体动作描写（过肩摔、锁喉、一脚踹飞），加入音效词（砰！咔嚓！）\n"
                    "  第4步「霸气收尾」: 用一句短台词钉死场面\n"
                    "    - ✅ \"下一个，谁来？\"  ✅ \"还有谁？\"\n"
                    "    - ❌ \"你们不要太过分了\"（太弱）\n"
                    "**禁忌**: 反击不超过5行；禁止反击时说大段独白；反击力度必须远超被欺辱程度"
                ),
            ),
            SatisfactionTemplate(
                id="identity_reveal", name="身份揭露/反转", level="big",
                prompt_text=(
                    "**情绪弧线**: 长期蒙蔽 → 证据浮现 → 石破天惊 → 认知崩塌\n"
                    "**四步行文**:\n"
                    "  第1步「信任铺垫」: 前文必须让观众也相信那个\"假象\"\n"
                    "  第2步「裂缝出现」: 一个细节让主角起疑（照片/言语失误/第三方爆料）\n"
                    "  第3步「真相揭露」: 用一句台词或一个画面彻底打碎假象\n"
                    "    - ✅ \"六年前，你体内的猎杀本能开始觉醒。他们把你当活体封印卖给了我\"\n"
                    "    - ✅ 照片上养父母穿着战甲踩着狼人残肢\n"
                    "  第4步「情绪核爆」: 特写听者的微表情——瞳孔地震、血色褪尽、双腿发软\n"
                    "**禁忌**: 真相不能由旁白交代，必须由角色亲口说出或亲眼看到"
                ),
            ),
            SatisfactionTemplate(
                id="brutal_protect", name="霸道守护", level="small",
                prompt_text=(
                    "**情绪弧线**: 爱人遇险 → 主角暴走 → 碾压级暴力 → 霸道宣示\n"
                    "**四步行文**:\n"
                    "  第1步「危机触发」: 反派直接威胁到主角的爱人（刀架在脖子上/被按倒）\n"
                    "  第2步「暴走瞬间」: 主角瞬间爆发，用 1-2 行写出从人到兽的切换\n"
                    "    - ✅ \"Dominic发出一声震天怒吼，甚至没有闪避，徒手接住毒刃\"\n"
                    "  第3步「碾压解决」: 用极端暴力迅速解决威胁（单手捏断颈骨/一口咬断喉咙）\n"
                    "  第4步「占有宣示」: 解决威胁后立刻把爱人拉入怀中+霸气台词\n"
                    "    - ✅ \"只要我还没死，谁也别想动她一根汗毛\"\n"
                    "**禁忌**: 暴力场面不能超过4行；守护后必须有温柔反差"
                ),
            ),
            SatisfactionTemplate(
                id="forbidden_attraction", name="禁忌吸引/情感突破", level="medium",
                prompt_text=(
                    "**情绪弧线**: 理智克制 → 身体背叛 → 防线崩溃 → 沦陷瞬间\n"
                    "**四步行文**:\n"
                    "  第1步「理智对抗」: 主角明确告诉自己不该爱（他是仇人/她是囚徒）\n"
                    "  第2步「身体背叛」: 不可控的物理反应——心跳加速/呼吸急促/瞳孔放大\n"
                    "    - ✅ \"触碰的瞬间，一股电流般的战栗感席卷全身，她的狼性突然苏醒\"\n"
                    "  第3步「关键触碰」: 一个不经意的接触打破最后防线（指尖相触/无意拥抱）\n"
                    "  第4步「沦陷台词」: 用极简的一个词/一句话表达彻底沦陷\n"
                    "    - ✅ \"伴侣……\"（颤抖低语）  ✅ \"你的味道让我觉得很安全\"\n"
                    "**禁忌**: 不能直接跳到亲吻，必须有层层递进的身体反应铺垫"
                ),
            ),
            SatisfactionTemplate(
                id="desperate_reversal", name="困境逆袭", level="big",
                prompt_text=(
                    "**情绪弧线**: 绝望深渊 → 最后一丝希望 → 奇迹爆发 → 形势逆转\n"
                    "**四步行文**:\n"
                    "  第1步「绝境铺垫」: 把主角逼到最惨的境地（四面楚歌/重伤倒地/被宣判死刑）\n"
                    "    - 必须让观众真的觉得\"这次完了\"\n"
                    "  第2步「最后挣扎」: 主角在绝望中做出最后的努力（即使看起来毫无希望）\n"
                    "  第3步「奇迹降临」: 隐藏的力量/意外的援兵/被遗忘的伏笔在最后一刻激活\n"
                    "    - ✅ \"掌心升腾起黑紫色的雾气，紫色光芒在昏暗中爆发生辉\"\n"
                    "  第4步「碾压翻盘」: 逆转必须彻底——从被按在地上到把对手按在地上\n"
                    "**禁忌**: 逆袭前的绝望必须够深，否则逆袭无感；禁止deus ex machina式的突兀救援"
                ),
            ),
            SatisfactionTemplate(
                id="truth_bomb", name="真相炸弹", level="big",
                prompt_text=(
                    "**情绪弧线**: 信仰坚固 → 裂缝出现 → 真相砸下 → 世界观崩塌\n"
                    "**四步行文**:\n"
                    "  第1步「信仰确立」: 前文反复强化主角对某事/某人的信任\n"
                    "    - ✅ \"我父亲是仁慈的领袖\" 重复多次\n"
                    "  第2步「证据逼近」: 第三方提供的线索开始动摇信仰\n"
                    "  第3步「残酷揭露」: 用最直接、最残忍的方式呈现真相\n"
                    "    - ✅ \"我当时只有十岁，躲在灌木丛里，看着他割断了我母亲的喉咙\"\n"
                    "    - ❌ \"你父亲不是好人\"（太笼统）\n"
                    "  第4步「崩塌表现」: 用肢体语言写出内心崩塌——跪倒、捂脸痛哭、发出灵魂被撕裂般的呜咽\n"
                    "**禁忌**: 真相必须有具体细节，不能只是抽象结论"
                ),
            ),
            SatisfactionTemplate(
                id="gap_moe", name="极致反差萌", level="small",
                prompt_text=(
                    "**情绪弧线**: 强者印象 → 意外软肋暴露 → 笨拙掩饰 → 观众心动\n"
                    "**四步行文**:\n"
                    "  第1步「强者形象」: 前文刚刚展示过角色的强大/冷酷/威严\n"
                    "  第2步「软肋暴露」: 因为爱人相关的事情，露出完全相反的一面\n"
                    "    - ✅ 暴君Alpha为采药受伤，被发现后耳根泛红\n"
                    "    - ✅ 冷酷王者整夜淋冷水保护昏迷的伴侣，拒绝趁人之危\n"
                    "  第3步「笨拙掩饰」: 角色试图掩饰软肋，但越掩饰越明显\n"
                    "    - ✅ \"迅速且狼狈地拉高衣领遮住伤口，耳根泛起违和的微红\"\n"
                    "  第4步「观众视角」: 通过第三者的惊讶/吐槽来放大反差效果\n"
                    "**禁忌**: 反差不能破坏角色核心人设；软肋只能在特定对象面前暴露"
                ),
            ),
            SatisfactionTemplate(
                id="stance_choice", name="立场选择", level="medium",
                prompt_text=(
                    "**情绪弧线**: 两难困境 → 所有人屏息 → 出人意料的选择 → 意义升华\n"
                    "**四步行文**:\n"
                    "  第1步「两难构建」: 两个选项都有不可承受的代价（父亲vs伴侣/安全vs正义）\n"
                    "  第2步「压力叠加」: 双方都在施压，时间在流逝\n"
                    "    - ✅ 父亲伸出手微笑 vs 身后伴侣在微微颤抖\n"
                    "  第3步「关键动作」: 用一个具体的肢体动作表达选择（推开一只手/靠进一个怀抱）\n"
                    "    - ✅ \"她用力推开了父亲伸过来的手，决绝地靠进了Theo的怀抱\"\n"
                    "  第4步「金句定音」: 一句掷地有声的台词升华选择的意义\n"
                    "    - ✅ \"我已经在家了\" ✅ \"家就在伴侣身边\"\n"
                    "**禁忌**: 选择必须有代价，不能两全其美；禁止用内心独白解释为什么选"
                ),
            ),
        ]

        self._hooks = [
            HookTemplate(
                id="action_cut", name="动作截断",
                prompt_text=(
                    "**公式**: [致命动作发出] + [命中前最后一帧的定格描写] + [强制黑屏]\n"
                    "**写法要求**:\n"
                    "  1. 动作必须是致命的/不可逆的（开枪/挥刀/扑杀）\n"
                    "  2. 必须写出动作的轨迹和速度感（破空而出/直逼心脏/撕裂空气）\n"
                    "  3. 在命中前0.1秒切断画面——绝不能写\"命中了\"或\"没命中\"\n"
                    "**✅ 范例**:\n"
                    "  \"Chloe咬牙扣动扳机。嗖！涂着致命银粉的弩箭撕破空气，"
                    "直逼Dominic的心脏！画面瞬间黑屏。\"\n"
                    "**❌ 禁忌**: 不能写\"箭射中了/没射中\"——答案必须留给下一集"
                ),
            ),
            HookTemplate(
                id="identity_bomb", name="身份炸弹",
                prompt_text=(
                    "**公式**: [角色说出石破天惊的一句话] + [听者微表情特写] + [定格]\n"
                    "**写法要求**:\n"
                    "  1. 这句话必须颠覆观众之前建立的认知（身份/关系/动机）\n"
                    "  2. 台词要短而精——不超过20个字，像一把刀直插心脏\n"
                    "  3. 必须写出听者的生理反应（瞳孔骤缩/血色褪尽/浑身僵住）\n"
                    "**✅ 范例**:\n"
                    "  \"Dominic: '你太聪明了，Elena。'——他钢蓝色的眼眸如深渊般死死盯着她。\"\n"
                    "  \"Elena: '原来真正的怪物……是我的父亲。'——画面定格在她惨白绝望的脸上。\"\n"
                    "**❌ 禁忌**: 信息量不能太大（那是正文的事），钩子只负责\"投下炸弹\""
                ),
            ),
            HookTemplate(
                id="crisis_break", name="危机降临",
                prompt_text=(
                    "**公式**: [温馨/浪漫的最高点] + [突然的暴力打断] + [角色瞬间切换战备]\n"
                    "**写法要求**:\n"
                    "  1. 打断前的温馨/浪漫必须写到极致——让观众完全沉浸其中\n"
                    "  2. 打断必须是物理性的（警报/爆炸/门被撞开），不能是心理活动\n"
                    "  3. 最后一行必须是角色从柔情切换到杀气的瞬间\n"
                    "**✅ 范例**:\n"
                    "  \"两人吻得难舍难分——'哔——！！！'尖锐的警报哨声撕裂空气——"
                    "Dominic猛地睁开双眼，钢蓝色眼眸充满野兽的警觉。\"\n"
                    "**❌ 禁忌**: 打断不能太温和（\"有人敲门\"太弱），必须是暴力级别的突入"
                ),
            ),
            HookTemplate(
                id="mutation_hint", name="异变暗示",
                prompt_text=(
                    "**公式**: [角色不经意的动作] + [身体出现异常征兆] + [画面定格在异变上]\n"
                    "**写法要求**:\n"
                    "  1. 异变必须是视觉化的（眼睛变色/指甲伸长/皮肤纹路/伤口自愈）\n"
                    "  2. 角色本人可以不知道发生了什么（更有悬念感）\n"
                    "  3. 用\"竟然\"\"诡异地\"\"不属于人类的\"等词强化异常感\n"
                    "**✅ 范例**:\n"
                    "  \"她原本温暖的棕色眼眸深处，竟诡异地闪过一丝不属于人类的、"
                    "极其危险的猩红光芒！画面定格。\"\n"
                    "**❌ 禁忌**: 不能解释异变的原因——留给下一集"
                ),
            ),
            HookTemplate(
                id="choice_cliffhanger", name="选择悬念",
                prompt_text=(
                    "**公式**: [两个都不可接受的选项] + [角色的手/目光在犹豫] + [黑屏不给答案]\n"
                    "**写法要求**:\n"
                    "  1. 两个选项都必须有巨大代价，观众无法猜测角色会选哪个\n"
                    "  2. 用肢体语言表现犹豫（手指悬在半空/目光在两人间游移）\n"
                    "  3. 在做出选择的前一秒切断画面\n"
                    "**✅ 范例**:\n"
                    "  \"Elena的手指悬在他的发丝上方，眼神复杂到了极点，"
                    "不知该推开，还是该落下。\"\n"
                    "**❌ 禁忌**: 绝不能给出选择结果"
                ),
            ),
            HookTemplate(
                id="dark_watcher", name="暗处窥视",
                prompt_text=(
                    "**公式**: [前景角色毫无察觉] + [镜头缓缓拉远到暗角] + [冰冷的眼睛/冷笑] + [黑屏]\n"
                    "**写法要求**:\n"
                    "  1. 前景必须是温馨/安全的场景（角色以为危险已经过去）\n"
                    "  2. 镜头转移要有\"缓缓\"的感觉，制造不安的气氛\n"
                    "  3. 暗处的存在只用一个细节暗示（一双眼睛/一声冷笑/一个剪影）\n"
                    "**✅ 范例**:\n"
                    "  \"镜头缓缓拉远，透过半掩的房门——一双阴冷的眼睛正躲在暗处，"
                    "死死监视着房间里的一举一动。伴随一声极其轻微的冷笑，画面黑屏。\"\n"
                    "**❌ 禁忌**: 不能揭示窥视者的身份（那是下一集的悬念）"
                ),
            ),
            HookTemplate(
                id="metaphor_detail", name="隐喻细节",
                prompt_text=(
                    "**公式**: [观众期待结果A] + [实际出现反常的结果B] + [角色震惊+留白]\n"
                    "**写法要求**:\n"
                    "  1. 反常细节必须是具体的、可视化的（门没锁/伤口消失/物品移位）\n"
                    "  2. 这个细节必须暗示着更深层的含义（信任/阴谋/力量觉醒）\n"
                    "  3. 不要解释含义——让观众自己去脑补\n"
                    "**✅ 范例**:\n"
                    "  \"她下意识握住门把手，准备承受被锁死的绝望——门竟然没有锁。"
                    "他给了她逃跑的机会，却用信任给她戴上了最沉重的枷锁。\"\n"
                    "**❌ 禁忌**: 不能用旁白解读隐喻含义，但可以用一句内心独白点题"
                ),
            ),
        ]


# 全局单例
prompt_template_manager = PromptTemplateManager()
