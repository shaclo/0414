"""快速逻辑自检脚本（单次运行，无 UI）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ─── 1. 导入检查 ─────────────────────────────────────────────
from models.data_models import HaugeStage
from models.project_state import ProjectData
from env import PERSONA_DEFINITIONS, SUGGESTED_TEMPERATURES
from services.ai_service import ai_service
from services.persona_engine import persona_engine
from services.ite_calculator import ite_calculator
from services.rag_controller import rag_controller
from services.worker import (
    SocraticWorker, WorldExtractWorker, CPGSkeletonWorker,
    VariationWorker, ITEWorker, RAGWorker,
)
print("[1] All imports OK")

# ─── 2. ProjectData 序列化往返 ────────────────────────────────
os.makedirs("projects", exist_ok=True)
pd = ProjectData()
pd.sparkle = "test sparkle"
pd.world_variables = [
    {"id": "v1", "category": "世界规则", "name": "测试", "definition": "定义", "constraints": "无"}
]
pd.confirmed_beats = {
    "N1": {"persona_name": "test", "causal_events": [], "entities": [], "hook": ""}
}
pd.cpg_nodes = [
    {
        "node_id": "N1", "title": "开端", "hauge_stage_id": 1,
        "hauge_stage_name": "机会", "event_summaries": ["事件1"],
        "setting": "", "characters": [],
    }
]
pd.save_to_file("projects/_check.story.json")
pd2 = ProjectData.load_from_file("projects/_check.story.json")
assert pd2.sparkle == "test sparkle"
assert pd2.confirmed_beats.get("N1") is not None
os.remove("projects/_check.story.json")
print("[2] ProjectData save/load round-trip OK")

# ─── 3. PersonaEngine build_variation_calls ───────────────────
persona_engine.set_active_personas(["historical_researcher", "scifi_futurist"])
calls = persona_engine.build_variation_calls(
    sparkle="测试种子",
    world_variables_json='{"vars":[]}',
    cpg_skeleton_json='{"nodes":[],"edges":[]}',
    target_node_id="N1",
    target_node_title="开端",
    hauge_stage_name="机会 (Opportunity)",
    node_event_summaries="事件1、事件2",
    previous_confirmed_beats_json="{}",
)
assert len(calls) == 2
assert all(k in calls[0] for k in ["user_prompt", "system_prompt", "persona_key", "temperature"])
assert "测试种子" in calls[0]["user_prompt"]
print(f"[3] PersonaEngine build_variation_calls OK: {len(calls)} calls")

# ─── 4. ITE 冗余筛选 ──────────────────────────────────────────
ite_mock = {
    "event_evaluations": [
        {"node_id": "N1", "event_id": 1, "ite_score": 0.02, "verdict": "冗余", "reasoning": "X"},
        {"node_id": "N1", "event_id": 2, "ite_score": 0.80, "verdict": "关键", "reasoning": "Y"},
    ]
}
prunable = ite_calculator.get_prunable_events(ite_mock, threshold=0.05)
assert len(prunable) == 1 and prunable[0]["event_id"] == 1
print("[4] ITECalculator.get_prunable_events OK")

# ─── 5. HaugeStage 枚举 ───────────────────────────────────────
assert HaugeStage.from_stage_id(3).cn_name == "无路可退"
assert HaugeStage.from_stage_id(1).en_name == "Opportunity"
assert HaugeStage.from_stage_id(5).cn_name == "高潮"
print("[5] HaugeStage enum OK")

# ─── 6. get_confirmed_beat_count ─────────────────────────────
pd3 = ProjectData()
pd3.confirmed_beats = {"N1": {"a": 1}, "N2": None, "N3": {"b": 2}}
assert pd3.get_confirmed_beat_count() == 2
print("[6] get_confirmed_beat_count OK")

# ─── 7. push_history 测试 ─────────────────────────────────────
pd4 = ProjectData()
pd4.push_history("lock_world")
pd4.push_history("generate_skeleton")
assert len(pd4.generation_history) == 2
assert pd4.generation_history[1]["action"] == "generate_skeleton"
print("[7] push_history OK")

# ─── 8. RAG str.replace 检查 ─────────────────────────────────
# 不实际调用 AI，只验证 prompt 装配不会抛 KeyError
from env import USER_PROMPT_RAG_CHECK
assembled = (
    USER_PROMPT_RAG_CHECK
    .replace("{new_beat_json}", '{"test":1}')
    .replace("{world_variables_json}", "[]")
    .replace("{confirmed_beats_json}", "{}")
)
assert '{"test":1}' in assembled
print("[8] RAG prompt assembly OK")

print()
print("=" * 50)
print("✅ 全部逻辑检查通过！程序逻辑正确。")
print("=" * 50)
