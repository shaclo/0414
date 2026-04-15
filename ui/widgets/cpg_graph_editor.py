# ============================================================
# ui/widgets/cpg_graph_editor.py
# CPG 可视化图编辑器
# 基于 QGraphicsView，支持：
#   - 拖拽节点（左键点击节点）
#   - 拖拽画布（左键点击空白区域）
#   - 拖拽连线（从 out_port 拖到 in_port 创建新边）
#   - 双击边编辑因果类型和描述
#   - 删除边（选中边后按 Delete）
#   - 滚轮缩放
# ============================================================

import math
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsPathItem, QGraphicsEllipseItem,
    QGraphicsDropShadowEffect, QWidget, QVBoxLayout,
    QDialog, QFormLayout, QComboBox, QLineEdit, QTextEdit,
    QDialogButtonBox, QLabel,
)
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QPainter, QPainterPath, QPen, QColor, QFont,
    QBrush, QPainterPathStroker,
)

# ============================================================
# Hauge 阶段对应的配色
# ============================================================
STAGE_COLORS = {
    1: "#e74c3c",   # 机会 — 红色
    2: "#f39c12",   # 变点 — 橙色
    3: "#9b59b6",   # 无路可退 — 紫色
    4: "#2c3e50",   # 主攻/挫折 — 深蓝
    5: "#e67e22",   # 高潮 — 深橙
    6: "#27ae60",   # 终局 — 绿色
}

# 可选的因果关系类型
CAUSAL_TYPES = [
    "直接因果",
    "情感驱动",
    "并行主题",
    "伏笔回收",
    "时间跳跃",
    "对比反转",
    "角色成长",
    "冲突升级",
    "信息揭示",
    "环境变化",
]


# ============================================================
# 边属性编辑对话框
# ============================================================
class EdgeEditDialog(QDialog):
    """编辑因果边的属性：因果类型 + 描述"""

    def __init__(self, causal_type: str = "", description: str = "",
                 from_name: str = "", to_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑连线属性")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        # 显示连线方向
        if from_name and to_name:
            direction = QLabel(f"📎 连线方向：{from_name}  →  {to_name}")
            direction.setStyleSheet("font-weight: bold; color: #2980b9; padding: 4px;")
            layout.addWidget(direction)

        form = QFormLayout()

        # 因果类型（下拉框 + 可自定义输入）
        self._type_combo = QComboBox()
        self._type_combo.setEditable(True)  # 可自定义输入
        self._type_combo.addItems(CAUSAL_TYPES)
        if causal_type:
            idx = self._type_combo.findText(causal_type)
            if idx >= 0:
                self._type_combo.setCurrentIndex(idx)
            else:
                self._type_combo.setCurrentText(causal_type)
        form.addRow("因果类型：", self._type_combo)

        # 描述
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText(
            "描述这两个节点之间的剧情走向关系...\n"
            "例如：主角在N1的决定直接导致了N2中的冲突爆发"
        )
        self._desc_edit.setMinimumHeight(80)
        self._desc_edit.setMaximumHeight(120)
        if description:
            self._desc_edit.setPlainText(description)
        form.addRow("关系描述：", self._desc_edit)

        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self) -> dict:
        return {
            "causal_type": self._type_combo.currentText().strip(),
            "description": self._desc_edit.toPlainText().strip(),
        }


class CPGPortItem(QGraphicsEllipseItem):
    """CPG 节点上的端口（连接点）"""
    def __init__(self, port_type, parent):
        super().__init__(-6, -6, 12, 12, parent)
        self.port_type = port_type  # 'in' | 'out'
        self.edges = []
        self.setBrush(QBrush(QColor("#95a5a6")))
        self.setPen(QPen(QColor("white"), 1.5))
        self.setCursor(Qt.CrossCursor)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(QColor("#e74c3c")))
        self.setScale(1.4)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(QColor("#95a5a6")))
        self.setScale(1.0)
        super().hoverLeaveEvent(event)


class CPGEdgeItem(QGraphicsPathItem):
    """CPG 图中的因果边（带箭头的贝塞尔曲线）"""
    def __init__(self, source_port=None, dest_port=None):
        super().__init__()
        self.source_port = source_port
        self.dest_port = dest_port
        self.floating_pos = QPointF()
        self.causal_type = ""
        self.description = ""

        if self.source_port:
            self.source_port.edges.append(self)
        if self.dest_port:
            self.dest_port.edges.append(self)

        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(-1)
        self.update_path()

    def update_path(self):
        start = self.source_port.scenePos() if self.source_port else self.floating_pos
        end = self.dest_port.scenePos() if self.dest_port else self.floating_pos
        path = QPainterPath(start)
        dx = end.x() - start.x()
        offset = max(abs(dx) * 0.4, 50)
        ctrl1 = QPointF(start.x() + offset, start.y())
        ctrl2 = QPointF(end.x() - offset, end.y())
        path.cubicTo(ctrl1, ctrl2, end)
        self.setPath(path)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(15)
        return stroker.createStroke(self.path())

    def paint(self, painter, option, widget=None):
        # 颜色根据因果类型变化
        if self.isSelected():
            color = QColor("#e74c3c")
            width = 3.5
        else:
            color = self._type_color()
            width = 2.5

        painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        path = self.path()
        painter.drawPath(path)

        # 箭头
        if path.length() > 10:
            p1 = path.pointAtPercent(0.97)
            p2 = path.pointAtPercent(1.0)
            angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
            arrow_size = 10
            p3 = QPointF(p2.x() - arrow_size * math.cos(angle - math.pi / 6),
                         p2.y() - arrow_size * math.sin(angle - math.pi / 6))
            p4 = QPointF(p2.x() - arrow_size * math.cos(angle + math.pi / 6),
                         p2.y() - arrow_size * math.sin(angle + math.pi / 6))
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon([p2, p3, p4])

        # 因果类型标签
        if self.causal_type:
            center = path.pointAtPercent(0.5)
            painter.setPen(QPen(QColor("#555")))
            painter.setFont(QFont("Microsoft YaHei", 8, QFont.Bold))
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(self.causal_type)
            # 半透明背景
            bg_rect = QRectF(center.x() - tw / 2 - 4, center.y() - 14, tw + 8, 16)
            painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bg_rect, 3, 3)
            painter.setPen(QPen(self._type_color()))
            painter.drawText(center.x() - tw / 2, center.y() - 2, self.causal_type)

    def _type_color(self) -> QColor:
        """根据因果类型返回不同颜色"""
        colors = {
            "直接因果": QColor("#7f8c8d"),
            "情感驱动": QColor("#e74c3c"),
            "并行主题": QColor("#3498db"),
            "伏笔回收": QColor("#9b59b6"),
            "时间跳跃": QColor("#1abc9c"),
            "对比反转": QColor("#e67e22"),
            "角色成长": QColor("#27ae60"),
            "冲突升级": QColor("#c0392b"),
            "信息揭示": QColor("#2980b9"),
            "环境变化": QColor("#16a085"),
        }
        return colors.get(self.causal_type, QColor("#bdc3c7"))

    def detach(self):
        """从端口列表中移除自身"""
        if self.source_port and self in self.source_port.edges:
            self.source_port.edges.remove(self)
        if self.dest_port and self in self.dest_port.edges:
            self.dest_port.edges.remove(self)


class CPGNodeItem(QGraphicsItem):
    """CPG 图中的节点（代表一个 Hauge 阶段中的事件组）"""
    def __init__(self, node_id, title, stage_id, status="pending"):
        super().__init__()
        self.node_id = node_id
        self.title = title
        self.stage_id = stage_id
        self.status = status
        self.color = STAGE_COLORS.get(stage_id, "#3498db")

        self.rect = QRectF(0, 0, 180, 60)

        self.in_port = CPGPortItem('in', self)
        self.in_port.setPos(0, self.rect.height() / 2)
        self.out_port = CPGPortItem('out', self)
        self.out_port.setPos(self.rect.width(), self.rect.height() / 2)

        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 30))
        self.setGraphicsEffect(shadow)

    def boundingRect(self):
        return self.rect.adjusted(-8, -8, 8, 8)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)

        if self.isSelected():
            painter.setPen(QPen(QColor(self.color), 2.5))
        else:
            painter.setPen(Qt.NoPen)

        bg_color = "#f0f9f0" if self.status == "confirmed" else "white"
        painter.setBrush(QBrush(QColor(bg_color)))
        painter.drawRoundedRect(self.rect, 8, 8)

        painter.setBrush(QBrush(QColor(self.color)))
        painter.setPen(Qt.NoPen)
        bar_path = QPainterPath()
        bar_path.addRoundedRect(QRectF(0, 0, 6, self.rect.height()), 3, 3)
        painter.drawPath(bar_path)

        painter.setPen(QColor("#aaa"))
        painter.setFont(QFont("Microsoft YaHei", 8))
        painter.drawText(QRectF(12, 2, 50, 16), Qt.AlignLeft | Qt.AlignVCenter, self.node_id)

        status_icon = {"pending": "⬜", "in_progress": "🔲", "confirmed": "✅"}.get(self.status, "⬜")
        painter.drawText(QRectF(self.rect.width() - 25, 2, 20, 16),
                        Qt.AlignRight | Qt.AlignVCenter, status_icon)

        painter.setPen(QColor("#333"))
        painter.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        painter.drawText(QRectF(12, 18, self.rect.width() - 24, 24),
                        Qt.AlignLeft | Qt.AlignVCenter, self.title)

        painter.setPen(QColor(self.color))
        painter.setFont(QFont("Microsoft YaHei", 8))
        stage_names = {1: "机会", 2: "变点", 3: "无路可退", 4: "挫折", 5: "高潮", 6: "终局"}
        stage_text = stage_names.get(self.stage_id, "")
        painter.drawText(QRectF(12, 42, self.rect.width() - 24, 16),
                        Qt.AlignLeft | Qt.AlignVCenter, stage_text)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for edge in self.in_port.edges + self.out_port.edges:
                edge.update_path()
            # 拖动后实时回写位置
            if hasattr(self, '_on_moved') and self._on_moved:
                self._on_moved(self.node_id, value)
        return super().itemChange(change, value)


# ============================================================
# 自定义 GraphicsView
# ============================================================
class CPGGraphicsView(QGraphicsView):
    """
    自定义 QGraphicsView:
    - 左键空白 → 拖画布
    - 左键节点 → 拖节点
    - 左键 out_port → 拖线到 in_port → 弹出属性对话框 → 创建新边
    - 双击边 → 编辑因果类型
    - Delete → 删除选中的边
    - 滚轮 → 缩放
    """

    edge_created = Signal(object)     # CPGEdgeItem
    edge_deleted = Signal(str, str)   # (from_node_id, to_node_id)
    edge_edited = Signal()            # 边属性被编辑

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor("#f8f9fa")))
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

        self._dragging_edge = False
        self._temp_edge = None
        self._drag_source_port = None
        self._panning = False
        self._pan_start = QPointF()

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 0.87
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)

        scene_pos = self.mapToScene(event.pos())
        item = self.scene().itemAt(scene_pos, self.transform())

        # 1. 点击 out_port → 开始拖拽连线
        if isinstance(item, CPGPortItem) and item.port_type == 'out':
            self._dragging_edge = True
            self._drag_source_port = item
            self._temp_edge = CPGEdgeItem(source_port=item)
            self._temp_edge.floating_pos = scene_pos
            self._temp_edge.update_path()
            self.scene().addItem(self._temp_edge)
            return

        # 2. 点击节点 → 拖动节点
        if isinstance(item, CPGNodeItem) or (item and isinstance(item.parentItem(), CPGNodeItem)):
            return super().mousePressEvent(event)

        # 3. 点击边 → 选中（但不拖画布）
        if isinstance(item, CPGEdgeItem):
            return super().mousePressEvent(event)

        # 4. 空白 → 拖画布
        self._panning = True
        self._pan_start = event.pos()
        self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """双击边 → 编辑因果类型"""
        scene_pos = self.mapToScene(event.pos())
        item = self.scene().itemAt(scene_pos, self.transform())

        if isinstance(item, CPGEdgeItem):
            self._edit_edge(item)
            return

        super().mouseDoubleClickEvent(event)

    def _edit_edge(self, edge: CPGEdgeItem):
        """弹出编辑对话框修改边的因果类型和描述"""
        src_node = edge.source_port.parentItem() if edge.source_port else None
        dst_node = edge.dest_port.parentItem() if edge.dest_port else None
        from_name = f"{src_node.node_id}: {src_node.title}" if src_node else ""
        to_name = f"{dst_node.node_id}: {dst_node.title}" if dst_node else ""

        dlg = EdgeEditDialog(
            causal_type=edge.causal_type,
            description=edge.description,
            from_name=from_name,
            to_name=to_name,
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            edge.causal_type = data["causal_type"]
            edge.description = data["description"]
            edge.update()  # 重绘
            self.edge_edited.emit()

    def mouseMoveEvent(self, event):
        if self._dragging_edge and self._temp_edge:
            scene_pos = self.mapToScene(event.pos())
            self._temp_edge.floating_pos = scene_pos
            self._temp_edge.update_path()

            item = self.scene().itemAt(scene_pos, self.transform())
            if isinstance(item, CPGPortItem) and item.port_type == 'in':
                item.setBrush(QBrush(QColor("#27ae60")))
                item.setScale(1.5)
            return

        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y()))
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging_edge:
            scene_pos = self.mapToScene(event.pos())
            item = self.scene().itemAt(scene_pos, self.transform())

            if (isinstance(item, CPGPortItem) and item.port_type == 'in'
                    and self._drag_source_port):
                src_node = self._drag_source_port.parentItem()
                dst_node = item.parentItem()

                if src_node and dst_node and src_node != dst_node:
                    already_exists = any(
                        e.source_port == self._drag_source_port and e.dest_port == item
                        for e in self._drag_source_port.edges
                        if e != self._temp_edge
                    )
                    if not already_exists:
                        self._cleanup_temp_edge()

                        # 弹出属性对话框
                        from_name = f"{src_node.node_id}: {src_node.title}"
                        to_name = f"{dst_node.node_id}: {dst_node.title}"
                        dlg = EdgeEditDialog(
                            causal_type="直接因果",
                            from_name=from_name,
                            to_name=to_name,
                            parent=self,
                        )
                        if dlg.exec() == QDialog.Accepted:
                            data = dlg.get_data()
                            new_edge = CPGEdgeItem(self._drag_source_port, item)
                            new_edge.causal_type = data["causal_type"]
                            new_edge.description = data["description"]
                            self.scene().addItem(new_edge)
                            self.edge_created.emit(new_edge)
                        # 如果取消，不创建边
                    else:
                        self._cleanup_temp_edge()
                else:
                    self._cleanup_temp_edge()
            else:
                self._cleanup_temp_edge()

            # 重置端口外观
            for item_in_scene in self.scene().items():
                if isinstance(item_in_scene, CPGPortItem):
                    item_in_scene.setBrush(QBrush(QColor("#95a5a6")))
                    item_in_scene.setScale(1.0)

            self._dragging_edge = False
            self._drag_source_port = None
            return

        if event.button() == Qt.LeftButton and self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)

        super().mouseReleaseEvent(event)

    def _cleanup_temp_edge(self):
        if self._temp_edge:
            self._temp_edge.detach()
            self.scene().removeItem(self._temp_edge)
            self._temp_edge = None

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            selected = self.scene().selectedItems()
            for item in selected:
                if isinstance(item, CPGEdgeItem):
                    src_node = item.source_port.parentItem() if item.source_port else None
                    dst_node = item.dest_port.parentItem() if item.dest_port else None
                    item.detach()
                    self.scene().removeItem(item)
                    if src_node and dst_node:
                        self.edge_deleted.emit(src_node.node_id, dst_node.node_id)
            return
        super().keyPressEvent(event)


class CPGGraphEditor(QWidget):
    """
    CPG 可视化图编辑器容器。

    信号:
        node_selected: 节点被选中时发出，参数为 node_id
        node_double_clicked: 节点被双击时发出
        edges_changed: 连线发生变化时发出（创建/删除/编辑边）
    """

    node_selected = Signal(str)
    node_double_clicked = Signal(str)
    edges_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes = {}
        self._edges = []
        self._loading = False
        self._cpg_nodes_ref = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._scene = QGraphicsScene()
        self._scene.setSceneRect(-2000, -2000, 4000, 4000)
        self._scene.selectionChanged.connect(self._on_selection_changed)

        self._view = CPGGraphicsView(self._scene)
        self._view.edge_created.connect(self._on_edge_created)
        self._view.edge_deleted.connect(self._on_edge_deleted)
        self._view.edge_edited.connect(self._on_edge_edited)
        layout.addWidget(self._view)

    def _on_selection_changed(self):
        selected = self._scene.selectedItems()
        for item in selected:
            if isinstance(item, CPGNodeItem):
                self.node_selected.emit(item.node_id)
                return

    def _on_edge_created(self, edge):
        if self._loading:
            return
        self._edges = [item for item in self._scene.items() if isinstance(item, CPGEdgeItem)]
        self.edges_changed.emit()

    def _on_edge_deleted(self, from_id: str, to_id: str):
        if self._loading:
            return
        self._edges = [item for item in self._scene.items() if isinstance(item, CPGEdgeItem)]
        self.edges_changed.emit()

    def _on_edge_edited(self):
        if self._loading:
            return
        self.edges_changed.emit()

    def _save_node_positions(self):
        """把图中所有节点的当前位置写回 cpg_nodes 数据"""
        if not hasattr(self, '_cpg_nodes_ref'):
            return
        for node_data in self._cpg_nodes_ref:
            nid = node_data.get("node_id", "")
            if nid in self._nodes:
                pos = self._nodes[nid].pos()
                node_data["pos_x"] = pos.x()
                node_data["pos_y"] = pos.y()

    def load_cpg(self, nodes: list, edges: list):
        # 保存引用，便于拖动后回写位置
        self._cpg_nodes_ref = nodes

        # 封锁 edges_changed 信号，防止 scene.clear() 时误触发
        self._loading = True
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()

        x, y = 0, 0
        col = 0
        for node_data in nodes:
            node_item = CPGNodeItem(
                node_id=node_data["node_id"],
                title=node_data.get("title", ""),
                stage_id=node_data.get("hauge_stage_id", 1),
                status=node_data.get("status", "pending"),
            )
            # 优先读取已保存的位置，否则用默认网格
            if "pos_x" in node_data and "pos_y" in node_data:
                node_item.setPos(node_data["pos_x"], node_data["pos_y"])
            else:
                node_item.setPos(x, y)
            node_item._on_moved = self._on_node_position_changed
            self._scene.addItem(node_item)
            self._nodes[node_data["node_id"]] = node_item

            col += 1
            x += 250
            if col >= 4:
                col = 0
                x = 0
                y += 120

        for edge_data in edges:
            src_id = edge_data["from_node"]
            dst_id = edge_data["to_node"]
            if src_id in self._nodes and dst_id in self._nodes:
                src_node = self._nodes[src_id]
                dst_node = self._nodes[dst_id]
                edge = CPGEdgeItem(src_node.out_port, dst_node.in_port)
                edge.causal_type = edge_data.get("causal_type", "")
                edge.description = edge_data.get("description", "")
                self._scene.addItem(edge)
                self._edges.append(edge)

        self._loading = False

    def _on_node_position_changed(self, node_id: str, pos):
        """节点被拖动后实时写回 pos_x/pos_y"""
        if not hasattr(self, '_cpg_nodes_ref'):
            return
        for node_data in self._cpg_nodes_ref:
            if node_data.get("node_id") == node_id:
                node_data["pos_x"] = pos.x()
                node_data["pos_y"] = pos.y()
                break

    def get_edges_data(self) -> list:
        result = []
        for item in self._scene.items():
            if not isinstance(item, CPGEdgeItem):
                continue
            src_node = item.source_port.parentItem() if item.source_port else None
            dst_node = item.dest_port.parentItem() if item.dest_port else None
            if src_node and dst_node:
                result.append({
                    "from_node": src_node.node_id,
                    "to_node": dst_node.node_id,
                    "causal_type": item.causal_type or "",
                    "description": item.description or "",
                })
        return result

    def update_node_status(self, node_id: str, status: str):
        if node_id in self._nodes:
            self._nodes[node_id].status = status
            self._nodes[node_id].update()

    def update_node_id(self, old_id: str, new_id: str):
        """更新节点 ID（同时更新边引用）"""
        if old_id not in self._nodes:
            return
        node_item = self._nodes.pop(old_id)
        node_item.node_id = new_id
        node_item.update()
        self._nodes[new_id] = node_item

    def get_node_ids(self) -> list:
        return list(self._nodes.keys())

    def clear_graph(self):
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()
