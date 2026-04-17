"""Unit tests for new skeleton node features"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 1. Imports
from ui.main_window import MainWindow
from ui.widgets.node_detail_dialog import NodeDetailDialog
from ui.widgets.split_dialog import SplitDialog
from services.worker import NodeRefineWorker
from models.project_state import make_node_snapshot, apply_snapshot, add_version, get_active_version_snapshot
from env import (SYSTEM_PROMPT_NODE_CHAT, SYSTEM_PROMPT_NODE_QUICK_REGEN,
                 SYSTEM_PROMPT_NODE_BVSR_REWRITE, SYSTEM_PROMPT_NODE_SPLIT_REFINE,
                 SYSTEM_PROMPT_NODE_MERGE)
print("[1] All imports OK")

# 2. Version functions
node = {
    'title': 'T', 'setting': 'S', 'characters': ['A'],
    'event_summaries': ['e1'], 'emotional_tone': 'happy', 'episode_hook': 'hook'
}
snap = make_node_snapshot(node)
assert snap['title'] == 'T'
assert snap['characters'] == ['A']

add_version(node, 'ai_generate', 'v0')
assert node['active_version'] == 0
assert len(node['versions']) == 1

apply_snapshot(node, {
    'title': 'T2', 'setting': 'S2', 'characters': ['B'],
    'event_summaries': ['e2'], 'emotional_tone': 'sad', 'episode_hook': 'h2'
})
assert node['title'] == 'T2'

add_version(node, 'manual', 'v1')
assert node['active_version'] == 1

snap2 = get_active_version_snapshot(node)
assert snap2['title'] == 'T2'
print("[2] Version functions OK")

# 3. parse_ep_num
from ui.phase2_skeleton import Phase2Skeleton
assert Phase2Skeleton._parse_ep_num('Ep3.1.2') == (3, 1, 2)
assert Phase2Skeleton._parse_ep_num('Ep3') == (3,)
assert Phase2Skeleton._parse_ep_num('Ep10.2') == (10, 2)
assert Phase2Skeleton._parse_ep_num('') == (0,)
# Sorting test
ids = ['Ep3.2', 'Ep1', 'Ep3.1.1', 'Ep3.1', 'Ep10', 'Ep2']
sorted_ids = sorted(ids, key=Phase2Skeleton._parse_ep_num)
assert sorted_ids == ['Ep1', 'Ep2', 'Ep3.1', 'Ep3.1.1', 'Ep3.2', 'Ep10'], f"Got: {sorted_ids}"
print("[3] parse_ep_num + sorting OK")

# 4. JSON parsing
import json
test_json = json.dumps({"title": "X", "event_summaries": []})
assert NodeRefineWorker._parse_node_json(test_json) is not None
assert NodeRefineWorker._parse_node_json('no json here') is None

arr_json = json.dumps([{"title": "A"}, {"title": "B"}])
assert len(NodeRefineWorker._parse_nodes_array(arr_json)) == 2
assert NodeRefineWorker._extract_modify_json('just text') is None

# Test modify detection with code block
modify_text = '```json\n{"action":"modify","node":{"title":"new"}}\n```'
result = NodeRefineWorker._extract_modify_json(modify_text)
assert result == {'title': 'new'}, f"Got: {result}"
print("[4] JSON parsing + modify detection OK")

# 5. Prompt templates contain placeholders
assert '{node_id}' in SYSTEM_PROMPT_NODE_CHAT
assert '{persona_identity_block}' in SYSTEM_PROMPT_NODE_QUICK_REGEN
assert '{persona_identity_block}' in SYSTEM_PROMPT_NODE_BVSR_REWRITE
assert '{split_count}' in SYSTEM_PROMPT_NODE_SPLIT_REFINE
assert '{drama_style_block}' in SYSTEM_PROMPT_NODE_MERGE
print("[5] Prompt placeholders OK")

print()
print("=" * 50)
print("ALL UNIT TESTS PASSED")
print("=" * 50)
