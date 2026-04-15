# ============================================================
# ui/widgets/cpg_graph_editor.py
# CPG 可视化图编辑器
# 基于 QGraphicsView，支持拖拽节点、连线、选中、编辑
# 原型参考：examplepaper/draganddropcard.py
# ============================================================

import math
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsPathItem, QGraphicsEllipseItem,
    QGraphicsDropShadowEffect, QWidget, QVBoxLayout,
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


class CPGPortItem(QGraphicsEllipseItem):
    """CPG 节点上的端口（连接点）"""
    def __init__(self, port_type, parent):
        super().__init__(-5, -5, 10, 10, parent)
        self.port_type = port_type  # 'in' | 'out'
        self.edges = []
        self.setBrush(QBrush(QColor("#95a5a6")))
        self.setPen(QPen(QColor("white"), 1.5))
        self.setCursor(Qt.CrossCursor)
        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(QColor("#e74c3c")))
        self.setScale(1.3)
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
        color = QColor("#e74c3c") if self.isSelected() else QColor("#bdc3c7")
        painter.setPen(QPen(color, 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
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
            painter.setPen(QPen(QColor("#888")))
            painter.setFont(QFont("Microsoft YaHei", 8))
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(self.causal_type)
            painter.drawText(center.x() - tw / 2, center.y() - 8, self.causal_type)


class CPGNodeItem(QGraphicsItem):
    """CPG 图中的节点（代表一个 Hauge 阶段中的事件组）"""
    def __init__(self, node_id, title, stage_id, status="pending"):
        super().__init__()
        self.node_id = node_id
        self.title = title
        self.stage_id = stage_id
        self.status = status  # pending | in_progress | confirmed
        self.color = STAGE_COLORS.get(stage_id, "#3498db")

        self.rect = QRectF(0, 0, 180, 60)

        # 输入/输出端口
        self.in_port = CPGPortItem('in', self)
        self.in_port.setPos(0, self.rect.height() / 2)
        self.out_port = CPGPortItem('out', self)
        self.out_port.setPos(self.rect.width(), self.rect.height() / 2)

        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        # 阴影效果
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 30))
        self.setGraphicsEffect(shadow)

    def boundingRect(self):
        return self.rect.adjusted(-8, -8, 8, 8)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)

        # 选中高亮
        if self.isSelected():
            painter.setPen(QPen(QColor(self.color), 2.5))
        else:
            painter.setPen(Qt.NoPen)

        # 背景
        bg_color = "#f0f9f0" if self.status == "confirmed" else "white"
        painter.setBrush(QBrush(QColor(bg_color)))
        painter.drawRoundedRect(self.rect, 8, 8)

        # 左侧色条
        painter.setBrush(QBrush(QColor(self.color)))
        painter.setPen(Qt.NoPen)
        bar_path = QPainterPath()
        bar_path.addRoundedRect(QRectF(0, 0, 6, self.rect.height()), 3, 3)
        painter.drawPath(bar_path)

        # 节点 ID
        painter.setPen(QColor("#aaa"))
        painter.setFont(QFont("Microsoft YaHei", 8))
        painter.drawText(QRectF(12, 2, 50, 16), Qt.AlignLeft | Qt.AlignVCenter, self.node_id)

        # 状态标记
        status_icon = {"pending": "⬜", "in_progress": "🔲", "confirmed": "✅"}.get(self.status, "⬜")
        painter.drawText(QRectF(self.rect.width() - 25, 2, 20, 16),
                        Qt.AlignRight | Qt.AlignVCenter, status_icon)

        # 标题
        painter.setPen(QColor("#333"))
        painter.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        painter.drawText(QRectF(12, 18, self.rect.width() - 24, 24),
                        Qt.AlignLeft | Qt.AlignVCenter, self.title)

        # Hauge 阶段标签
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
        return super().itemChange(change, value)


class CPGGraphEditor(QWidget):
    """
    CPG 可视化图编辑器容器。
    封装 QGraphicsView + QGraphicsScene，提供节点/边的增删改查接口。

    信号:
        node_selected: 节点被选中时发出，参数为 node_id
        node_double_clicked: 节点被双击时发出，参数为 node_id
    """

    node_selected = Signal(str)
    node_double_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes = {}        # node_id -> CPGNodeItem
        self._edges = []        # CPGEdgeItem list
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._scene = QGraphicsScene()
        self._scene.setSceneRect(-2000, -2000, 4000, 4000)
        # 节点选中变化 → 发出信号
        self._scene.selectionChanged.connect(self._on_selection_changed)

        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.Antialiasing)
        self._view.setBackgroundBrush(QBrush(QColor("#f8f9fa")))
        self._view.setDragMode(QGraphicsView.RubberBandDrag)
        self._view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._view.wheelEvent = self._wheel_zoom  # 支持滚轮缩放
        layout.addWidget(self._view)

    def _on_selection_changed(self):
        """场景选中变化时发出 node_selected 信号"""
        selected = self._scene.selectedItems()
        for item in selected:
            if isinstance(item, CPGNodeItem):
                self.node_selected.emit(item.node_id)
                return

    def _wheel_zoom(self, event):
        """滚轮缩放"""
        factor = 1.15 if event.angleDelta().y() > 0 else 0.87
        self._view.scale(factor, factor)

    def load_cpg(self, nodes: list, edges: list):
        """
        加载 CPG 数据到图编辑器。

        Args:
            nodes: [{"node_id": "N1", "title": "...", "hauge_stage_id": 1, "status": "pending"}]
            edges: [{"from_node": "N1", "to_node": "N2", "causal_type": "...", "description": "..."}]
        """
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()

        # 创建节点（自动排列）
        x, y = 0, 0
        col = 0
        for node_data in nodes:
            node_item = CPGNodeItem(
                node_id=node_data["node_id"],
                title=node_data.get("title", ""),
                stage_id=node_data.get("hauge_stage_id", 1),
                status=node_data.get("status", "pending"),
            )
            node_item.setPos(x, y)
            self._scene.addItem(node_item)
            self._nodes[node_data["node_id"]] = node_item

            col += 1
            x += 250
            if col >= 4:  # 每行最多排 4 个
                col = 0
                x = 0
                y += 120

        # 创建边
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

    def update_node_status(self, node_id: str, status: str):
        """更新节点状态（pending/in_progress/confirmed）"""
        if node_id in self._nodes:
            self._nodes[node_id].status = status
            self._nodes[node_id].update()

    def get_node_ids(self) -> list:
        """获取所有节点 ID"""
        return list(self._nodes.keys())

    def clear_graph(self):
        """清空图"""
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()
