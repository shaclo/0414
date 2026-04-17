"""
V2 全量接口审计脚本 — 13项原有 + 5项新增
覆盖 Character/CharacterRelation/Phase2/Phase5/ExpansionWorker
"""
import os, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = "[OK]  "
FAIL = "[FAIL]"
results = []

def check(label, fn):
    try:
        fn()
        results.append((PASS, label, ""))
    except Exception as e:
        results.append((FAIL, label, traceback.format_exc(limit=3)))

# ── 1. models.data_models (含新类) ────────────────────────────
def t_data_models():
    from models.data_models import (
        HaugeStage, CausalEvent, StoryBeat, WorldVariable,
        QAPair, CPGNode, CausalEdge, HaugeStageData,
        Character, CharacterRelation,
    )
    c = Character(char_id="char_001", name="李明", role_type="主角",
                  position="流亡皇子", personality="机敏、隐忍")
    assert c.to_dict()["name"] == "李明"
    assert "主角" in c.to_prompt_summary()
    assert "机敏" in c.to_prompt_summary()

    cr = CharacterRelation(from_char_id="char_001", to_char_id="char_002",
                           relation_type="父子/敌对")
    assert cr.to_dict()["relation_type"] == "父子/敌对"

    c2 = Character.from_dict(c.to_dict())
    assert c2.name == "李明"

check("models.data_models — Character + CharacterRelation", t_data_models)

# ── 2. models.project_state (含新字段) ───────────────────────
def t_project_state():
    from models.project_state import ProjectData
    import json, tempfile, os
    pd = ProjectData()
    pd.sparkle = "测试"
    pd.characters = [{"char_id": "char_001", "name": "李明"}]
    pd.character_relations = [{"from_char_id": "char_001", "to_char_id": "char_002",
                                "relation_type": "父子"}]
    pd.screenplay_texts = {"Ep1": "场景1 剧本正文..."}
    with tempfile.NamedTemporaryFile(suffix=".story.json", delete=False,
                                     mode="w", encoding="utf-8") as f:
        fname = f.name
    try:
        pd.save_to_file(fname)
        pd2 = ProjectData.load_from_file(fname)
        assert pd2.characters[0]["name"] == "李明"
        assert pd2.character_relations[0]["relation_type"] == "父子"
        assert pd2.screenplay_texts["Ep1"] == "场景1 剧本正文..."
    finally:
        os.unlink(fname)

check("models.project_state — characters/relations/screenplay_texts 往返", t_project_state)

# ── 3. env.py (含新Prompt) ─────────────────────────────────────
def t_env():
    import env
    for attr in [
        "SYSTEM_PROMPT_SOCRATIC", "SYSTEM_PROMPT_WORLD_EXTRACT",
        "SYSTEM_PROMPT_CPG_SKELETON", "USER_PROMPT_CPG_SKELETON",
        "SYSTEM_PROMPT_VARIATION_FRAME",
        "SYSTEM_PROMPT_ITE", "SYSTEM_PROMPT_RAG_CHECK",
        "SYSTEM_PROMPT_CHARACTER_GEN", "USER_PROMPT_CHARACTER_GEN",
        "SYSTEM_PROMPT_EXPANSION", "USER_PROMPT_EXPANSION",
        "TEMPERATURE_CHARACTER_GEN", "TEMPERATURE_EXPANSION",
        "PERSONA_DEFINITIONS", "SUGGESTED_TEMPERATURES",
    ]:
        assert hasattr(env, attr), f"缺少: {attr}"
    # 检查角色占位符注入
    assert "{characters_summary}" in env.USER_PROMPT_CPG_SKELETON
    assert "{characters_summary}" in env.USER_PROMPT_EXPANSION
    assert "{target_word_count}" in env.SYSTEM_PROMPT_EXPANSION
    assert len(env.PERSONA_DEFINITIONS) == 10

check("env.py — 新增Prompt + 占位符完整性", t_env)

# ── 4. services.worker (含新Worker) ──────────────────────────
def t_workers():
    from services.worker import (
        BaseWorker, SocraticWorker, WorldExtractWorker,
        CPGSkeletonWorker, VariationWorker, ITEWorker, RAGWorker,
        CharacterGenWorker, ExpansionWorker,
    )
    # 新Worker构造（不启动）
    w_char = CharacterGenWorker("测试梗概", [], "终局条件", {"temperature": 0.5})
    assert w_char.sparkle == "测试梗概"

    w_exp = ExpansionWorker(
        sparkle="测试",
        finale_condition="终局",
        characters_summary="• 李明 [主角]",
        previous_hook="故事开篇",
        node_id="Ep1", node_title="开始",
        hauge_stage_name="机会",
        setting="皇宫", entities="李明、张将军",
        causal_events_text="  事件1...",
        hook="悬念",
        target_word_count="600-800",
        ai_params={"temperature": 0.7},
    )
    assert w_exp.node_id == "Ep1"
    assert w_exp.target_word_count == "600-800"

    # CPGSkeletonWorker 支持 characters 参数
    w_cpg = CPGSkeletonWorker("梗概", [], "终局", {"temperature": 0.6},
                               characters=[{"char_id": "char_001", "name": "李明"}])
    assert len(w_cpg.characters) == 1

    # VariationWorker 支持 characters 参数
    w_var = VariationWorker(
        sparkle="梗概", world_variables=[], cpg_nodes=[], cpg_edges=[],
        target_node={"node_id": "Ep1", "title": "开始"},
        confirmed_beats={}, selected_persona_keys=["historical_researcher"],
        ai_params={"temperature": 1.0},
        characters=[{"char_id": "char_001", "name": "李明"}],
    )
    assert len(w_var.characters) == 1

check("services.worker — CharacterGenWorker + ExpansionWorker + 角色注入", t_workers)

# ── 5. proxyserverconfig (间隔更新) ───────────────────────────
def t_proxy():
    from proxyserverconfig import MIN_CALL_INTERVAL, MAX_CALL_INTERVAL
    assert MIN_CALL_INTERVAL == 1, f"期望1, 实际{MIN_CALL_INTERVAL}"
    assert MAX_CALL_INTERVAL == 5, f"期望5, 实际{MAX_CALL_INTERVAL}"

check("proxyserverconfig — 间隔缩短为1-5s", t_proxy)

# ── 6. ui widgets（含新Widget) ────────────────────────────────
def t_ui_widgets():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from ui.widgets.ai_settings_panel import AISettingsPanel
    from ui.widgets.prompt_viewer import PromptViewer
    from ui.widgets.persona_selector import PersonaSelector
    from ui.widgets.beat_card import BeatCard
    from ui.widgets.cpg_graph_editor import CPGGraphEditor
    from ui.widgets.qa_panel import QAPanel
    from ui.widgets.world_var_table import WorldVarTable
    from ui.widgets.character_editor import CharacterEditor
    from ui.widgets.character_relation_panel import CharacterRelationPanel
    from ui.widgets.screenplay_editor import ScreenplayEditor

    # 实例化新Widget
    ce = CharacterEditor()
    ce.load_character({"char_id": "c1", "name": "李明", "role_type": "主角",
                        "gender": "男", "age": "25", "position": "皇子",
                        "personality": "机敏", "motivation": "复仇",
                        "appearance": "清瘦", "notes": ""})
    d = ce.get_current_dict()
    assert d["name"] == "李明"

    crp = CharacterRelationPanel()
    crp.set_characters([{"char_id": "c1", "name": "李明"},
                         {"char_id": "c2", "name": "皇帝"}])
    crp.set_relations([{"from_char_id": "c1", "to_char_id": "c2",
                         "relation_type": "父子/敌对", "description": ""}])
    assert len(crp.get_relations()) == 1

    se = ScreenplayEditor(target_min=600, target_max=800)
    se.set_text("场景1 内容...")
    assert "场景1" in se.get_text()
    tmin, tmax = se.get_target_range()
    assert tmin == 600 and tmax == 800

check("ui.widgets — character_editor + relation_panel + screenplay_editor", t_ui_widgets)

# ── 7. ui phases (含新Phase) ─────────────────────────────────
def t_ui_phases():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from models.project_state import ProjectData
    pd = ProjectData()

    from ui.phase1_genesis import Phase1Genesis
    from ui.phase2_characters import Phase2Characters
    from ui.phase2_skeleton import Phase2Skeleton
    from ui.phase3_flesh import Phase3Flesh
    from ui.phase5_expansion import Phase5Expansion
    from ui.phase4_lock import Phase4Lock
    from ui.main_window import MainWindow

    w = MainWindow()
    assert w._stack.count() == 6, f"期望6个Phase, 实际{w._stack.count()}"
    assert len(w._phase_labels) == 6

check("ui.phases — 6个Phase + MainWindow实例化", t_ui_phases)

# ── 8. Phase2Characters on_enter ─────────────────────────────
def t_p2_on_enter():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from models.project_state import ProjectData
    from ui.phase2_characters import Phase2Characters
    pd = ProjectData()
    pd.characters = [
        {"char_id": "c1", "name": "李明", "role_type": "主角",
         "gender": "男", "age": "25", "position": "", "personality": "",
         "motivation": "", "appearance": "", "notes": ""},
    ]
    pd.character_relations = []
    p2 = Phase2Characters(pd)
    p2.on_enter()
    assert p2._char_list.count() == 1

check("ui.phase2_characters — on_enter + 角色列表渲染", t_p2_on_enter)

# ── 9. Phase5Expansion on_enter ──────────────────────────────
def t_p5_on_enter():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from models.project_state import ProjectData
    from ui.phase5_expansion import Phase5Expansion
    pd = ProjectData()
    pd.cpg_nodes = [
        {"node_id": "Ep1", "title": "开始", "hauge_stage_id": 1,
         "hauge_stage_name": "机会", "setting": "", "characters": [],
         "event_summaries": [], "emotional_tone": ""},
    ]
    pd.confirmed_beats = {"Ep1": {"setting": "皇宫", "entities": ["李明"],
                                   "causal_events": [], "hook": "悬念"}}
    pd.screenplay_texts = {}
    pd.characters = []
    p5 = Phase5Expansion(pd)
    p5.on_enter()
    assert p5._node_combo.count() == 1

check("ui.phase5_expansion — on_enter + 节点列表渲染", t_p5_on_enter)

# ── 10. Data Flow Phase2->Phase3->Phase5 ─────────────────────
def t_data_flow():
    from models.project_state import ProjectData
    pd = ProjectData()
    pd.characters = [{"char_id": "c1", "name": "李明", "role_type": "主角"}]
    pd.character_relations = [{"from_char_id": "c1", "to_char_id": "c2",
                                 "relation_type": "父子/敌对"}]
    pd.cpg_nodes = [
        {"node_id": "Ep1", "title": "开始", "hauge_stage_id": 1,
         "hauge_stage_name": "机会", "event_summaries": ["事件1"],
         "setting": "", "characters": ["李明"]},
        {"node_id": "Ep2", "title": "转折", "hauge_stage_id": 2,
         "hauge_stage_name": "变点", "event_summaries": ["事件2"],
         "setting": "", "characters": ["李明", "皇帝"]},
    ]
    pd.confirmed_beats = {"Ep1": None, "Ep2": None}
    pd.confirmed_beats["Ep1"] = {"causal_events": [], "setting": "皇宫",
                                  "entities": ["李明"], "hook": "悬念1"}
    pending = pd.get_pending_nodes()
    assert len(pending) == 1 and pending[0]["node_id"] == "Ep2"
    # 全部确认后screenplay_texts可独立填写
    pd.confirmed_beats["Ep2"] = {"causal_events": [], "setting": "密室",
                                  "entities": ["李明", "皇帝"], "hook": "悬念2"}
    pd.screenplay_texts["Ep1"] = "场景1剧本正文"
    pd.screenplay_texts["Ep2"] = "场景2剧本正文"
    assert len(pd.screenplay_texts) == 2

check("data_flow — Phase2→Phase3→Phase5 完整数据流", t_data_flow)

# ── 输出结果 ─────────────────────────────────────────────────
print("\n" + "="*65)
print("V2 全量接口审计报告")
print("="*65)
fail_count = 0
for status, label, msg in results:
    print(f"{status} {label}")
    if status == FAIL:
        fail_count += 1
        # 只打印最后几行错误
        lines = [l for l in msg.strip().split("\n") if l.strip()]
        for line in lines[-4:]:
            print(f"        {line}")
print("="*65)
print(f"总计: {len(results)} 项   通过: {len(results)-fail_count}   失败: {fail_count}")
print("="*65)
