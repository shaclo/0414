# ============================================================
# ui/widgets/character_graph_widget.py
# 人物关系力导向图 — 用 QGraphicsView 实现
# ============================================================

import math
import random
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem,
    QGraphicsTextItem, QGraphicsLineItem, QGraphicsItem,
    QGraphicsRectItem,
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialogButtonBox, QFormLayout, QComboBox,
    QLineEdit, QTextEdit, QGraphicsDropShadowEffect,
    QSlider, QGroupBox,
)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QPen, QBrush, QColor, QFont, QPainter, QPainterPath,
    QFontMetrics, QRadialGradient, QPolygonF,
)
from typing import List, Dict, Optional


# ============================================================
# 多策略 char_id 匹配工具
# ============================================================
def _match_char_id(identifier: str, char_id: str, char_name: str,
                   characters: list) -> bool:
    if not identifier:
        return False
    if identifier == char_id:
        return True
    if identifier == char_name:
        return True
    if identifier.startswith("char_"):
        try:
            idx = int(identifier.split("_")[1]) - 1
            if 0 <= idx < len(characters):
                target = characters[idx]
                if target.get("char_id") == char_id or target.get("name") == char_name:
                    return True
        except (ValueError, IndexError):
            pass
    return False


def _resolve_char_id(identifier: str, characters: list) -> Optional[str]:
    if not identifier:
        return None
    for c in characters:
        if c.get("char_id") == identifier:
            return identifier
    if identifier.startswith("char_"):
        try:
            idx = int(identifier.split("_")[1]) - 1
            if 0 <= idx < len(characters):
                return characters[idx].get("char_id", identifier)
        except (ValueError, IndexError):
            pass
    for c in characters:
        if c.get("name") == identifier:
            return c.get("char_id", identifier)
    return identifier


# ============================================================
# 角色关系详情对话框（双击角色卡片弹出）
# ============================================================
class CharRelationDetailDialog(QDialog):
    """显示并编辑指定角色的所有关系"""

    relations_changed = Signal()

    def __init__(self, char_id: str, char_name: str,
                 characters: list, relations: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{char_name} 的人物关系")
        self.setMinimumSize(640, 420)
        self._char_id = char_id
        self._char_name = char_name
        self._characters = characters
        self._relations = relations
        self._changed = False
        self._setup_ui()
        self._refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        info = QLabel(
            f"角色: {self._char_name} (ID: {self._char_id})  |  "
            f"展示该角色的所有出入方向关系"
        )
        info.setStyleSheet("color: #2c3e50;")
        layout.addWidget(info)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["方向", "关联角色", "关系类型", "说明"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self._table.setColumnWidth(0, 60)
        self._table.setColumnWidth(1, 120)
        self._table.setColumnWidth(2, 140)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.doubleClicked.connect(self._on_edit_relation)
        layout.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ 新增关系")
        btn_add.clicked.connect(self._on_add)
        btn_row.addWidget(btn_add)
        btn_del = QPushButton("- 删除选中")
        btn_del.clicked.connect(self._on_delete)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.accept)
        layout.addWidget(btns)

    def _get_name(self, cid: str) -> str:
        if not cid:
            return "(未知)"
        for c in self._characters:
            if c.get("char_id") == cid:
                return c.get("name", cid)
        if cid.startswith("char_"):
            try:
                idx = int(cid.split("_")[1]) - 1
                if 0 <= idx < len(self._characters):
                    return self._characters[idx].get("name", cid)
            except (ValueError, IndexError):
                pass
        for c in self._characters:
            if c.get("name") == cid:
                return cid
        return cid

    def _my_relations(self) -> list:
        result = []
        for i, r in enumerate(self._relations):
            from_id = r.get("from_char_id", "")
            to_id = r.get("to_char_id", "")
            is_from = _match_char_id(from_id, self._char_id, self._char_name, self._characters)
            is_to = _match_char_id(to_id, self._char_id, self._char_name, self._characters)
            if is_from:
                result.append((i, "-> 出", r))
            elif is_to:
                result.append((i, "<- 入", r))
        return result

    def _refresh(self):
        rels = self._my_relations()
        self._table.setRowCount(len(rels))
        self._display_indices = []
        for row, (idx, direction, r) in enumerate(rels):
            self._display_indices.append(idx)
            other = r.get("to_char_id") if direction.startswith("->") else r.get("from_char_id")
            self._table.setItem(row, 0, QTableWidgetItem(direction))
            self._table.setItem(row, 1, QTableWidgetItem(self._get_name(other)))
            self._table.setItem(row, 2, QTableWidgetItem(r.get("relation_type", "")))
            self._table.setItem(row, 3, QTableWidgetItem(r.get("description", "")))

    def _on_add(self):
        if len(self._characters) < 2:
            QMessageBox.warning(self, "提示", "至少需要两个角色。")
            return
        from ui.widgets.character_relation_panel import RelationDialog
        chars = [{"char_id": c.get("char_id", ""), "name": c.get("name", "")}
                 for c in self._characters]
        initial = {"from_char_id": self._char_id, "to_char_id": "", "relation_type": "", "description": ""}
        dlg = RelationDialog(chars, self, initial=initial)
        if dlg.exec() == QDialog.Accepted:
            rel = dlg.get_relation()
            if rel.get("relation_type"):
                self._relations.append(rel)
                self._changed = True
                self._refresh()

    def _on_delete(self):
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()), reverse=True)
        for row in rows:
            if row < len(self._display_indices):
                real_idx = self._display_indices[row]
                if real_idx < len(self._relations):
                    del self._relations[real_idx]
                    self._changed = True
        self._refresh()

    def _on_edit_relation(self, index):
        row = index.row()
        if row < 0 or row >= len(self._display_indices):
            return
        real_idx = self._display_indices[row]
        if real_idx >= len(self._relations):
            return
        from ui.widgets.character_relation_panel import RelationDialog
        chars = [{"char_id": c.get("char_id", ""), "name": c.get("name", "")}
                 for c in self._characters]
        dlg = RelationDialog(chars, self, initial=self._relations[real_idx])
        if dlg.exec() == QDialog.Accepted:
            self._relations[real_idx] = dlg.get_relation()
            self._changed = True
            self._refresh()

    def accept(self):
        if self._changed:
            self.relations_changed.emit()
        super().accept()


# ============================================================
# 角色节点（可拖动 + 实时边更新）
# ============================================================
class CharacterNode(QGraphicsEllipseItem):
    """力导向图中的角色节点，拖动时实时更新连线"""

    IMPORTANCE_SIZE = {"A": 86, "B": 66, "C": 50}
    ROLE_COLORS = {
        "主角": ("#c0392b", "#ffffff"),
        "反派": ("#6c3483", "#ffffff"),
        "辅助": ("#1e8449", "#ffffff"),
        "配角": ("#2471a3", "#ffffff"),
        "群演": ("#566573", "#ecf0f1"),
    }

    def __init__(self, char_data: dict):
        self.char_data = char_data
        imp = char_data.get("importance_level", "C")
        self.node_size = self.IMPORTANCE_SIZE.get(imp, 50)
        super().__init__(-self.node_size/2, -self.node_size/2,
                         self.node_size, self.node_size)

        role_type = char_data.get("role_type", "配角")
        bg_color, fg_color = self.ROLE_COLORS.get(role_type, ("#2471a3", "#ffffff"))
        self.setBrush(QBrush(QColor(bg_color)))
        self.setPen(QPen(QColor("#2c3e50"), 2.5))

        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(10)

        # 名字标签
        name = char_data.get("name", "?")
        self._label = QGraphicsTextItem(name, self)
        font_size = 10 if imp == "A" else (9 if imp == "B" else 8)
        font = QFont("Microsoft YaHei", font_size, QFont.Bold)
        self._label.setFont(font)
        self._label.setDefaultTextColor(QColor(fg_color))
        br = self._label.boundingRect()
        self._label.setPos(-br.width()/2, -br.height()/2)

        # 重要度标记
        imp_text = {"A": "A", "B": "B", "C": "C"}.get(imp, "C")
        imp_label = QGraphicsTextItem(imp_text, self)
        imp_label.setFont(QFont("Microsoft YaHei", 7, QFont.Bold))
        imp_label.setDefaultTextColor(QColor("#f1c40f"))
        ibr = imp_label.boundingRect()
        imp_label.setPos(-ibr.width()/2, self.node_size/2 - 2)

        # 物理属性
        self.vx = 0.0
        self.vy = 0.0
        self._dragging = False
        # 连接的边（拖拽时实时更新）
        self._connected_edges: list = []

    def add_edge(self, edge):
        if edge not in self._connected_edges:
            self._connected_edges.append(edge)

    def char_id(self):
        return self.char_data.get("char_id", "")

    def mousePressEvent(self, event):
        self._dragging = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        # 拖动时实时更新所有连接的边
        for edge in self._connected_edges:
            edge.update_position()

    def is_dragging(self):
        return self._dragging


# ============================================================
# 关系边（带标签的连线）
# ============================================================
class RelationEdge:
    """两个角色之间的关系连线 + 标签"""

    def __init__(self, from_node: CharacterNode, to_node: CharacterNode,
                 relation: dict, scene: QGraphicsScene):
        self.from_node = from_node
        self.to_node = to_node
        self.relation = relation

        # 注册到节点上，拖拽时由节点触发 update_position
        from_node.add_edge(self)
        to_node.add_edge(self)

        # 连线
        self.line = QGraphicsLineItem()
        pen = QPen(QColor("#2c3e50"), 2.0, Qt.SolidLine)
        self.line.setPen(pen)
        self.line.setZValue(1)
        scene.addItem(self.line)

        # 标签
        label_text = relation.get("relation_type", "")
        if label_text:
            self.label_bg = QGraphicsRectItem()
            self.label_bg.setBrush(QBrush(QColor(255, 255, 255, 220)))
            self.label_bg.setPen(QPen(QColor("#bdc3c7"), 1))
            self.label_bg.setZValue(2)
            scene.addItem(self.label_bg)

            self.label = QGraphicsTextItem(label_text)
            self.label.setFont(QFont("Microsoft YaHei", 8))
            self.label.setDefaultTextColor(QColor("#2c3e50"))
            self.label.setZValue(3)
            scene.addItem(self.label)
        else:
            self.label = None
            self.label_bg = None

        # 箭头
        self.arrow = scene.addPolygon(
            QPolygonF([QPointF(0, -5), QPointF(10, 0), QPointF(0, 5)]),
            QPen(Qt.NoPen),
            QBrush(QColor("#2c3e50"))
        )
        self.arrow.setZValue(2)

    def update_position(self):
        p1 = self.from_node.scenePos()
        p2 = self.to_node.scenePos()
        self.line.setLine(p1.x(), p1.y(), p2.x(), p2.y())

        if self.label:
            mx = (p1.x() + p2.x()) / 2
            my = (p1.y() + p2.y()) / 2
            br = self.label.boundingRect()
            self.label.setPos(mx - br.width()/2, my - br.height()/2)
            pad = 3
            self.label_bg.setRect(
                mx - br.width()/2 - pad,
                my - br.height()/2 - pad,
                br.width() + pad*2,
                br.height() + pad*2,
            )

        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        dist = math.sqrt(dx*dx + dy*dy) or 1
        t = max(0, 1 - self.to_node.node_size / dist * 0.7)
        ax = p1.x() + dx * t
        ay = p1.y() + dy * t
        angle = math.degrees(math.atan2(dy, dx))
        self.arrow.setPos(ax, ay)
        self.arrow.setRotation(angle)

    def remove_from_scene(self, scene):
        scene.removeItem(self.line)
        if self.label:
            scene.removeItem(self.label)
        if self.label_bg:
            scene.removeItem(self.label_bg)
        scene.removeItem(self.arrow)


# ============================================================
# 布局算法
# ============================================================
LAYOUT_ALGORITHMS = {
    "force_directed": "弹簧力导向 (经典)",
    "protagonist_center": "主角为中心 (辐射)",
    "hierarchy_top_down": "重要程度层级 (上→下)",
    "circular": "环形布局 (舒展)",
}


def _layout_force_directed(nodes, edges, repulsion, spring_k, spring_len,
                           damping, center_gravity, steps=200):
    """经典弹簧-斥力力导向"""
    node_list = list(nodes.values())
    n = len(node_list)
    if n == 0:
        return

    for _ in range(steps):
        total_energy = 0
        for i, na in enumerate(node_list):
            fx, fy = 0.0, 0.0
            for j, nb in enumerate(node_list):
                if i == j:
                    continue
                dx = na.x() - nb.x()
                dy = na.y() - nb.y()
                dist = math.sqrt(dx*dx + dy*dy) or 1
                force = repulsion / (dist * dist)
                fx += force * dx / dist
                fy += force * dy / dist

            for edge in edges:
                other = None
                if edge.from_node is na:
                    other = edge.to_node
                elif edge.to_node is na:
                    other = edge.from_node
                if other:
                    dx = other.x() - na.x()
                    dy = other.y() - na.y()
                    dist = math.sqrt(dx*dx + dy*dy) or 1
                    force = spring_k * (dist - spring_len)
                    fx += force * dx / dist
                    fy += force * dy / dist

            fx -= center_gravity * na.x()
            fy -= center_gravity * na.y()

            na.vx = (na.vx + fx) * damping
            na.vy = (na.vy + fy) * damping
            na.setPos(na.x() + na.vx, na.y() + na.vy)
            total_energy += na.vx**2 + na.vy**2

        if total_energy < 0.5:
            break


def _layout_protagonist_center(nodes, characters, repulsion_base):
    """主角居中，其他角色按重要程度辐射"""
    node_list = list(nodes.values())
    if not node_list:
        return

    # 找主角 (importance A)
    a_nodes = [n for n in node_list if n.char_data.get("importance_level") == "A"]
    b_nodes = [n for n in node_list if n.char_data.get("importance_level") == "B"]
    c_nodes = [n for n in node_list if n.char_data.get("importance_level") == "C"]

    # 主角放中心
    spacing = repulsion_base / 40  # 用重力值控制间距
    for i, n in enumerate(a_nodes):
        angle = 2 * math.pi * i / max(len(a_nodes), 1)
        n.setPos(spacing * 0.3 * math.cos(angle), spacing * 0.3 * math.sin(angle))

    # B 级在中圈
    for i, n in enumerate(b_nodes):
        angle = 2 * math.pi * i / max(len(b_nodes), 1) + 0.3
        r = spacing * 1.2
        n.setPos(r * math.cos(angle), r * math.sin(angle))

    # C 级在外圈
    for i, n in enumerate(c_nodes):
        angle = 2 * math.pi * i / max(len(c_nodes), 1) + 0.15
        r = spacing * 2.2
        n.setPos(r * math.cos(angle), r * math.sin(angle))


def _layout_hierarchy(nodes, characters, repulsion_base):
    """从上到下的层级布局：A 在上, B 中间, C 在下"""
    node_list = list(nodes.values())
    if not node_list:
        return

    layers = {"A": [], "B": [], "C": []}
    for n in node_list:
        imp = n.char_data.get("importance_level", "C")
        layers.get(imp, layers["C"]).append(n)

    spacing_x = repulsion_base / 30
    spacing_y = repulsion_base / 20
    y_offset = 0

    for level in ["A", "B", "C"]:
        layer_nodes = layers[level]
        total_w = (len(layer_nodes) - 1) * spacing_x if layer_nodes else 0
        start_x = -total_w / 2
        for i, n in enumerate(layer_nodes):
            n.setPos(start_x + i * spacing_x, y_offset)
        if layer_nodes:
            y_offset += spacing_y


def _layout_circular(nodes, characters, repulsion_base):
    """环形布局 — 所有角色均匀分布在圆周上，A 级在内圈"""
    node_list = list(nodes.values())
    if not node_list:
        return

    # 按重要程度排序：A 先, 保证 A 在起始位置
    node_list.sort(key=lambda n: {"A": 0, "B": 1, "C": 2}.get(
        n.char_data.get("importance_level", "C"), 2))

    radius = repulsion_base / 15
    for i, n in enumerate(node_list):
        angle = 2 * math.pi * i / len(node_list) - math.pi / 2
        n.setPos(radius * math.cos(angle), radius * math.sin(angle))


# ============================================================
# 全屏图弹窗
# ============================================================
class GraphFullscreenDialog(QDialog):
    relations_changed = Signal()

    def __init__(self, characters, relations, parent=None):
        super().__init__(parent)
        self.setWindowTitle("人物关系全览")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)
        self._graph = CharacterGraphWidget(show_fullscreen_btn=False)
        self._graph.relations_changed.connect(self._on_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._graph, 1)
        btn = QPushButton("关闭")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, 0, Qt.AlignRight)
        self._graph.set_data(characters, relations)

    def _on_changed(self):
        self.relations_changed.emit()

    def get_relations(self):
        return self._graph.get_relations()


# ============================================================
# 力导向图主控件
# ============================================================
class CharacterGraphWidget(QWidget):
    """人物关系力导向图 — 多布局 + 重力滑块"""

    relations_changed = Signal()

    # 默认物理参数
    DEFAULT_REPULSION = 8000
    SPRING_K = 0.005
    SPRING_LEN = 180
    DAMPING = 0.85
    CENTER_GRAVITY = 0.01
    MIN_ENERGY = 0.5

    def __init__(self, parent=None, show_fullscreen_btn=True):
        super().__init__(parent)
        self._characters: List[dict] = []
        self._relations: List[dict] = []
        self._nodes: Dict[str, CharacterNode] = {}
        self._edges: List[RelationEdge] = []
        self._sim_running = False
        self._repulsion = self.DEFAULT_REPULSION
        self._current_layout = "force_directed"
        self._show_fullscreen_btn = show_fullscreen_btn
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ---- 工具条第一行 ----
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("人物关系图"))

        toolbar.addWidget(QLabel("  布局:"))
        self._layout_combo = QComboBox()
        self._layout_combo.setMinimumWidth(140)
        for key, label in LAYOUT_ALGORITHMS.items():
            self._layout_combo.addItem(label, key)
        self._layout_combo.currentIndexChanged.connect(self._on_layout_changed)
        toolbar.addWidget(self._layout_combo)

        btn_relayout = QPushButton("重新布局")
        btn_relayout.clicked.connect(self._restart_layout)
        toolbar.addWidget(btn_relayout)

        btn_fit = QPushButton("适应视图")
        btn_fit.clicked.connect(self._fit_view)
        toolbar.addWidget(btn_fit)

        if self._show_fullscreen_btn:
            btn_expand = QPushButton("全屏查看")
            btn_expand.setStyleSheet(
                "QPushButton{background:#2c3e50;color:white;font-weight:bold;"
                "border-radius:3px;border:none;padding:4px 10px;}"
                "QPushButton:hover{background:#34495e;}"
            )
            btn_expand.clicked.connect(self._on_expand)
            toolbar.addWidget(btn_expand)

        toolbar.addWidget(QLabel("  间距:"))
        self._gravity_slider = QSlider(Qt.Horizontal)
        self._gravity_slider.setMinimum(2000)
        self._gravity_slider.setMaximum(60000)
        self._gravity_slider.setValue(int(self._repulsion))
        self._gravity_slider.setTickInterval(2000)
        self._gravity_slider.setFixedWidth(200)
        self._gravity_slider.valueChanged.connect(self._on_gravity_changed)
        toolbar.addWidget(self._gravity_slider)
        self._gravity_label = QLabel(f"{self._repulsion:.0f}")
        self._gravity_label.setFixedWidth(45)
        self._gravity_label.setStyleSheet("color: #636e72;")
        toolbar.addWidget(self._gravity_label)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ---- 图形视图 ----
        self._scene = QGraphicsScene()
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHints(
            QPainter.Antialiasing | QPainter.TextAntialiasing
        )
        self._view.setDragMode(QGraphicsView.ScrollHandDrag)
        self._view.setMinimumHeight(280)
        self._view.setStyleSheet(
            "QGraphicsView { background: #ecf0f1; "
            "border: 1px solid #95a5a6; border-radius: 6px; }"
        )
        layout.addWidget(self._view, 1)

        # 模拟定时器
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._simulation_step)

        tip = QLabel("拖拽节点调整位置 | 双击角色查看/编辑关系 | 滚轮缩放")
        tip.setStyleSheet("color: #7f8c8d;")
        layout.addWidget(tip)

        self._view.wheelEvent = self._on_wheel

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #
    def set_data(self, characters: list, relations: list):
        self._characters = characters
        self._relations = relations
        self._rebuild_graph()

    def get_relations(self) -> list:
        return list(self._relations)

    # ------------------------------------------------------------------ #
    # 布局切换
    # ------------------------------------------------------------------ #
    def _on_layout_changed(self, index):
        key = self._layout_combo.itemData(index)
        if key and key != self._current_layout:
            self._current_layout = key
            self._restart_layout()

    def _on_gravity_changed(self, value):
        self._repulsion = float(value)
        self._gravity_label.setText(f"{self._repulsion:.0f}")
        # 实时重新布局
        self._restart_layout()

    # ------------------------------------------------------------------ #
    # 图构建
    # ------------------------------------------------------------------ #
    def _rebuild_graph(self):
        self._timer.stop()
        self._sim_running = False

        for edge in self._edges:
            edge.remove_from_scene(self._scene)
        self._edges.clear()
        for node in self._nodes.values():
            self._scene.removeItem(node)
        self._nodes.clear()

        if not self._characters:
            return

        # 创建节点
        importance_order = {"A": 0, "B": 1, "C": 2}
        sorted_chars = sorted(
            self._characters,
            key=lambda c: importance_order.get(c.get("importance_level", "C"), 2)
        )

        for i, char in enumerate(sorted_chars):
            node = CharacterNode(char)
            cid = char.get("char_id", f"node_{i}")
            # 初始随机位置
            node.setPos(random.uniform(-200, 200), random.uniform(-200, 200))
            self._scene.addItem(node)
            self._nodes[cid] = node

        # 创建边
        for rel in self._relations:
            from_id = rel.get("from_char_id", "")
            to_id = rel.get("to_char_id", "")
            from_node = self._find_node(from_id)
            to_node = self._find_node(to_id)
            if from_node and to_node and from_node != to_node:
                edge = RelationEdge(from_node, to_node, rel, self._scene)
                self._edges.append(edge)

        # 应用布局
        self._apply_layout()

        # 更新边位置
        for edge in self._edges:
            edge.update_position()

        QTimer.singleShot(100, self._fit_view)
        self._view.mouseDoubleClickEvent = self._on_double_click

    def _apply_layout(self):
        """根据当前选择的布局算法排列节点"""
        algo = self._current_layout

        if algo == "force_directed":
            # 先设初始位置
            imp_order = {"A": 0, "B": 1, "C": 2}
            sorted_nodes = sorted(self._nodes.values(),
                                  key=lambda n: imp_order.get(n.char_data.get("importance_level", "C"), 2))
            for i, node in enumerate(sorted_nodes):
                imp = node.char_data.get("importance_level", "C")
                radius = {"A": 50, "B": 160, "C": 260}.get(imp, 200)
                angle = 2 * math.pi * i / max(len(sorted_nodes), 1)
                node.setPos(radius * math.cos(angle), radius * math.sin(angle))
                node.vx = 0
                node.vy = 0

            # 启动逐帧模拟
            self._sim_running = True
            self._sim_steps = 0
            self._timer.start()

        elif algo == "protagonist_center":
            _layout_protagonist_center(self._nodes, self._characters, self._repulsion)

        elif algo == "hierarchy_top_down":
            _layout_hierarchy(self._nodes, self._characters, self._repulsion)

        elif algo == "circular":
            _layout_circular(self._nodes, self._characters, self._repulsion)

    def _find_node(self, identifier: str) -> Optional[CharacterNode]:
        if not identifier:
            return None
        if identifier in self._nodes:
            return self._nodes[identifier]
        for cid, node in self._nodes.items():
            if node.char_data.get("name") == identifier:
                return node
        if identifier.startswith("char_"):
            try:
                idx = int(identifier.split("_")[1]) - 1
                if 0 <= idx < len(self._characters):
                    target_cid = self._characters[idx].get("char_id", "")
                    if target_cid in self._nodes:
                        return self._nodes[target_cid]
            except (ValueError, IndexError):
                pass
        return None

    # ------------------------------------------------------------------ #
    # 物理模拟（仅 force_directed 使用）
    # ------------------------------------------------------------------ #
    def _simulation_step(self):
        if not self._sim_running:
            return

        nodes = list(self._nodes.values())
        n = len(nodes)
        if n == 0:
            self._timer.stop()
            return

        total_energy = 0.0

        for i, node_a in enumerate(nodes):
            if node_a.is_dragging():
                node_a.vx = 0
                node_a.vy = 0
                # 即使拖拽中也要更新边
                for edge in node_a._connected_edges:
                    edge.update_position()
                continue

            fx, fy = 0.0, 0.0

            for j, node_b in enumerate(nodes):
                if i == j:
                    continue
                dx = node_a.x() - node_b.x()
                dy = node_a.y() - node_b.y()
                dist = math.sqrt(dx*dx + dy*dy) or 1
                force = self._repulsion / (dist * dist)
                fx += force * dx / dist
                fy += force * dy / dist

            for edge in self._edges:
                other = None
                if edge.from_node is node_a:
                    other = edge.to_node
                elif edge.to_node is node_a:
                    other = edge.from_node
                if other:
                    dx = other.x() - node_a.x()
                    dy = other.y() - node_a.y()
                    dist = math.sqrt(dx*dx + dy*dy) or 1
                    force = self.SPRING_K * (dist - self.SPRING_LEN)
                    fx += force * dx / dist
                    fy += force * dy / dist

            fx -= self.CENTER_GRAVITY * node_a.x()
            fy -= self.CENTER_GRAVITY * node_a.y()

            node_a.vx = (node_a.vx + fx) * self.DAMPING
            node_a.vy = (node_a.vy + fy) * self.DAMPING

            node_a.setPos(node_a.x() + node_a.vx, node_a.y() + node_a.vy)
            total_energy += node_a.vx**2 + node_a.vy**2

        # 更新所有边
        for edge in self._edges:
            edge.update_position()

        self._sim_steps += 1
        if total_energy < self.MIN_ENERGY or self._sim_steps > 300:
            self._timer.stop()
            self._sim_running = False

    # ------------------------------------------------------------------ #
    # 交互
    # ------------------------------------------------------------------ #
    def _on_double_click(self, event):
        scene_pos = self._view.mapToScene(event.pos())
        item = self._scene.itemAt(scene_pos, self._view.transform())
        while item and not isinstance(item, CharacterNode):
            item = item.parentItem()
        if isinstance(item, CharacterNode):
            cid = item.char_id()
            cname = item.char_data.get("name", "?")
            dlg = CharRelationDetailDialog(
                cid, cname, self._characters, self._relations, self
            )
            dlg.relations_changed.connect(self._on_relations_edited)
            dlg.exec()

    def _on_relations_edited(self):
        self._rebuild_graph()
        self.relations_changed.emit()

    def _on_wheel(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._view.scale(factor, factor)

    def _restart_layout(self):
        self._rebuild_graph()

    def _fit_view(self):
        rect = self._scene.itemsBoundingRect()
        rect.adjust(-60, -60, 60, 60)
        self._view.fitInView(rect, Qt.KeepAspectRatio)

    def _on_expand(self):
        dlg = GraphFullscreenDialog(self._characters, self._relations, self.window())
        dlg.relations_changed.connect(self._on_fullscreen_changed)
        dlg.exec()
        new_rels = dlg.get_relations()
        if new_rels != self._relations:
            self._relations = new_rels
            self._rebuild_graph()
            self.relations_changed.emit()

    def _on_fullscreen_changed(self):
        pass
