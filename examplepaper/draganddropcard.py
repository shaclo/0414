import sys
import math
from PySide6.QtWidgets import (QApplication, QGraphicsView, QGraphicsScene, 
                               QGraphicsItem, QGraphicsPathItem, QGraphicsEllipseItem,
                               QGraphicsDropShadowEffect, QMainWindow, QToolBar,
                               QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QComboBox, QRadioButton, QCheckBox, QPushButton, QInputDialog)
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QPen, QColor, QFont, QBrush, QPainterPathStroker, QAction

# ==========================================
# 1. 基础组件：端口与连线 
# ==========================================

class PortItem(QGraphicsEllipseItem):
    def __init__(self, port_type, parent):
        super().__init__(-6, -6, 12, 12, parent)
        self.port_type = port_type 
        self.edges = []
        self.setBrush(QBrush(QColor("#95a5a6")))
        self.setPen(QPen(QColor("white"), 2))
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


class EdgeItem(QGraphicsPathItem):
    def __init__(self, source_port=None, dest_port=None):
        super().__init__()
        self.source_port = source_port
        self.dest_port = dest_port
        self.floating_pos = QPointF()
        self.edge_name = ""  # 🌟 新增：连线的命名属性
        
        if self.source_port: self.source_port.edges.append(self)
        if self.dest_port: self.dest_port.edges.append(self)
        
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(-1)
        self.update_path()

    def update_path(self):
        start_pos = self.source_port.scenePos() if self.source_port else self.floating_pos
        end_pos = self.dest_port.scenePos() if self.dest_port else self.floating_pos

        path = QPainterPath(start_pos)
        dx = end_pos.x() - start_pos.x()
        ctrl_offset = max(abs(dx) * 0.5, 60) 
        
        ctrl1 = QPointF(start_pos.x() + ctrl_offset, start_pos.y())
        ctrl2 = QPointF(end_pos.x() - ctrl_offset, end_pos.y())
        
        path.cubicTo(ctrl1, ctrl2, end_pos)
        self.setPath(path)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(20)
        return stroker.createStroke(self.path())

    def paint(self, painter, option, widget=None):
        color = QColor("#e74c3c") if self.isSelected() else QColor("#bdc3c7")
        painter.setPen(QPen(color, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        
        path = self.path()
        painter.drawPath(path)

        # 绘制箭头
        if path.length() > 10:
            p1, p2 = path.pointAtPercent(0.99), path.pointAtPercent(1.0)
            angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
            arrow_size = 12
            p3 = QPointF(p2.x() - arrow_size * math.cos(angle - math.pi / 6),
                         p2.y() - arrow_size * math.sin(angle - math.pi / 6))
            p4 = QPointF(p2.x() - arrow_size * math.cos(angle + math.pi / 6),
                         p2.y() - arrow_size * math.sin(angle + math.pi / 6))
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon([p2, p3, p4])

        # 🌟 新增：在线的中间位置绘制该线的名称（可选，为了更直观）
        if self.edge_name:
            center_pos = path.pointAtPercent(0.5)
            painter.setPen(QPen(color))
            painter.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(self.edge_name)
            painter.drawText(center_pos.x() - tw/2, center_pos.y() - 10, self.edge_name)

    # 🌟 新增：双击连线进行重命名
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            new_name, ok = QInputDialog.getText(None, "命名连线", "请输入连接线的名称:", text=self.edge_name)
            if ok:
                self.edge_name = new_name.strip()
                # 命名后，立刻通知相连的两个卡片刷新 UI 以显示新名字
                if self.source_port: self.source_port.parentItem().update()
                if self.dest_port: self.dest_port.parentItem().update()
                self.update() # 连线自身也刷新
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


# ==========================================
# 2. 独立对话框：双击卡片后弹出的属性面板
# ==========================================

class NodePropertiesDialog(QDialog):
    def __init__(self, node, parent=None):
        super().__init__(parent)
        self.node = node
        self.setWindowTitle(f"属性配置 - {node.node_type}")
        self.resize(320, 250)
        
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(15)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("节点名称:"))
        self.name_input = QLineEdit(node.title)
        name_layout.addWidget(self.name_input)
        self.layout.addLayout(name_layout)
        
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #ddd;")
        self.layout.addWidget(line)

        self.build_specific_ui()

        self.layout.addStretch()

        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("取消")
        btn_confirm = QPushButton("确认")
        btn_confirm.setStyleSheet("background-color: #3498db; color: white; font-weight: bold;")
        
        btn_cancel.clicked.connect(self.reject)
        btn_confirm.clicked.connect(self.accept)
        
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_confirm)
        self.layout.addLayout(btn_box)

    def build_specific_ui(self):
        if self.node.node_type == "触发事件":
            self.layout.addWidget(QLabel("参数配置:"))
            self.layout.addWidget(QLineEdit(placeholderText="输入参数 1..."))
            self.layout.addWidget(QLineEdit(placeholderText="输入参数 2..."))
            self.layout.addWidget(QLineEdit(placeholderText="输入参数 3..."))
            
        elif self.node.node_type == "逻辑条件":
            self.layout.addWidget(QLabel("逻辑判定:"))
            self.layout.addWidget(QLineEdit(placeholderText="判定基准数值..."))
            combo = QComboBox()
            combo.addItems(["大于 (>)", "小于 (<)", "等于 (==)", "不等于 (!=)"])
            self.layout.addWidget(combo)
            
        elif self.node.node_type == "数据处理":
            self.layout.addWidget(QLabel("处理模式:"))
            self.layout.addWidget(QRadioButton("开启深度清洗 (耗时更长)"))
            self.layout.addWidget(QRadioButton("普通模式 (默认)"))
            self.layout.addWidget(QCheckBox("忽略空值"))
            self.layout.addWidget(QCheckBox("去除重复项"))
            
        elif self.node.node_type == "结果输出":
            self.layout.addWidget(QLabel("输出设置:"))
            self.layout.addWidget(QLineEdit(placeholderText="指定输出文件名 (如 result.csv)"))
            self.layout.addWidget(QRadioButton("覆盖现有文件"))
            self.layout.addWidget(QCheckBox("导出完成时弹窗通知我"))


# ==========================================
# 3. 核心组件：极简卡片 (支持显示端口名称)
# ==========================================

class NodeItem(QGraphicsItem):
    def __init__(self, title, node_type, color="#3498db", num_in=1, num_out=1):
        super().__init__()
        self.title = title
        self.node_type = node_type
        self.color = color
        
        # 🌟 修改：加宽了卡片宽度，为两边显示连线名称留出空间
        card_height = max(70, max(num_in, num_out) * 30 + 20)
        self.rect = QRectF(0, 0, 200, card_height) 

        self.in_ports, self.out_ports = [], []
        for i in range(num_in):
            port = PortItem('in', self)
            port.setPos(0, self.rect.height() * (i + 1) / (num_in + 1))
            self.in_ports.append(port)

        for i in range(num_out):
            port = PortItem('out', self)
            port.setPos(self.rect.width(), self.rect.height() * (i + 1) / (num_out + 1))
            self.out_ports.append(port)

        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setFlag(QGraphicsItem.ItemIsSelectable) 

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(shadow)

    def boundingRect(self):
        return self.rect.adjusted(-10, -10, 10, 10)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        if self.isSelected():
            painter.setPen(QPen(QColor(self.color), 2))
        else:
            painter.setPen(Qt.NoPen)
            
        painter.setBrush(QBrush(QColor("white")))
        painter.drawRoundedRect(self.rect, 8, 8)

        painter.setBrush(QBrush(QColor(self.color)))
        painter.setPen(Qt.NoPen)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, 8, self.rect.height()), 8, 8)
        painter.drawPath(path)

        # 绘制主标题
        painter.setPen(QColor("#333333"))
        painter.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        # 标题居中靠上一点
        painter.drawText(QRectF(15, 5, self.rect.width()-30, 25), Qt.AlignCenter, self.title)

        # 🌟 新增：循环绘制两侧连线的名称
        painter.setFont(QFont("Microsoft YaHei", 8))
        painter.setPen(QColor("#7f8c8d")) # 浅灰色，不抢主标题风头

        # 遍历左侧入口，提取连接线的名字
        for port in self.in_ports:
            names = [e.edge_name for e in port.edges if e.edge_name]
            if names:
                text = ", ".join(names)
                # 在对应的小圆点右侧绘制文字
                painter.drawText(QRectF(15, port.pos().y() - 10, 80, 20), Qt.AlignLeft | Qt.AlignVCenter, text)

        # 遍历右侧出口，提取连接线的名字
        for port in self.out_ports:
            names = [e.edge_name for e in port.edges if e.edge_name]
            if names:
                text = ", ".join(names)
                # 在对应的小圆点左侧绘制文字
                painter.drawText(QRectF(self.rect.width() - 95, port.pos().y() - 10, 80, 20), Qt.AlignRight | Qt.AlignVCenter, text)


    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for port in self.in_ports + self.out_ports:
                for edge in port.edges:
                    edge.update_path()
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            dialog = NodePropertiesDialog(self)
            if dialog.exec() == QDialog.Accepted:
                self.title = dialog.name_input.text().strip()
                self.update() 
        super().mouseDoubleClickEvent(event)


# ==========================================
# 4. 画布视图与主程序
# ==========================================

class NodeEditorView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(-5000, -5000, 10000, 10000) 
        self.setScene(self.scene)
        
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor("#f4f5f7")))
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        
        self.dragging_edge = None
        self.drag_mode = None 

    def keyPressEvent(self, event):
        # 🌟 修改：删除连线时，主动通知相关的卡片刷新 UI
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in self.scene.selectedItems():
                if isinstance(item, EdgeItem):
                    if item.source_port: 
                        node = item.source_port.parentItem()
                        item.source_port.edges.remove(item)
                        node.update()
                    if item.dest_port: 
                        node = item.dest_port.parentItem()
                        item.dest_port.edges.remove(item)
                        node.update()
                    self.scene.removeItem(item)
                elif isinstance(item, NodeItem):
                    for port in item.in_ports + item.out_ports:
                        for edge in list(port.edges):
                            if edge.source_port: edge.source_port.edges.remove(edge)
                            if edge.dest_port: edge.dest_port.edges.remove(edge)
                            self.scene.removeItem(edge)
                    self.scene.removeItem(item)
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.scene.itemAt(self.mapToScene(event.pos()), self.transform())
            if isinstance(item, PortItem):
                self.dragging_edge = EdgeItem()
                self.scene.addItem(self.dragging_edge)
                if item.port_type == 'out':
                    self.dragging_edge.source_port = item
                    item.edges.append(self.dragging_edge)
                    self.drag_mode = 'dest'
                else:
                    self.dragging_edge.dest_port = item
                    item.edges.append(self.dragging_edge)
                    self.drag_mode = 'source'
                self.dragging_edge.floating_pos = self.mapToScene(event.pos())
                self.dragging_edge.update_path()
                return

            if isinstance(item, EdgeItem):
                click_pos = self.mapToScene(event.pos())
                dist_to_src = (item.source_port.scenePos() - click_pos).manhattanLength() if item.source_port else 999
                dist_to_dst = (item.dest_port.scenePos() - click_pos).manhattanLength() if item.dest_port else 999
                
                # 🌟 修改：拔线时也要更新卡片
                if dist_to_dst < 35 and item.dest_port:
                    node = item.dest_port.parentItem()
                    item.dest_port.edges.remove(item)
                    item.dest_port = None
                    node.update()
                    self.dragging_edge = item
                    self.drag_mode = 'dest'
                    self.dragging_edge.floating_pos = click_pos
                    return
                elif dist_to_src < 35 and item.source_port:
                    node = item.source_port.parentItem()
                    item.source_port.edges.remove(item)
                    item.source_port = None
                    node.update()
                    self.dragging_edge = item
                    self.drag_mode = 'source'
                    self.dragging_edge.floating_pos = click_pos
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging_edge:
            self.dragging_edge.floating_pos = self.mapToScene(event.pos())
            self.dragging_edge.update_path()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.dragging_edge:
            item = self.scene.itemAt(self.mapToScene(event.pos()), self.transform())
            connected = False
            if isinstance(item, PortItem):
                if self.drag_mode == 'dest' and item.port_type == 'in':
                    if not self.dragging_edge.source_port or item.parentItem() != self.dragging_edge.source_port.parentItem():
                        self.dragging_edge.dest_port = item
                        item.edges.append(self.dragging_edge)
                        connected = True
                elif self.drag_mode == 'source' and item.port_type == 'out':
                    if not self.dragging_edge.dest_port or item.parentItem() != self.dragging_edge.dest_port.parentItem():
                        self.dragging_edge.source_port = item
                        item.edges.append(self.dragging_edge)
                        connected = True
            
            # 🌟 修改：松开线头时，无论连接成功失败，都刷新受影响的卡片
            if not connected:
                if self.dragging_edge.source_port: 
                    self.dragging_edge.source_port.edges.remove(self.dragging_edge)
                    self.dragging_edge.source_port.parentItem().update()
                if self.dragging_edge.dest_port: 
                    self.dragging_edge.dest_port.edges.remove(self.dragging_edge)
                    self.dragging_edge.dest_port.parentItem().update()
                self.scene.removeItem(self.dragging_edge)
            else:
                self.dragging_edge.update_path()
                if self.dragging_edge.source_port: self.dragging_edge.source_port.parentItem().update()
                if self.dragging_edge.dest_port: self.dragging_edge.dest_port.parentItem().update()
                
            self.dragging_edge = None
        else:
            super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 蓝图编辑器 - 最终完美连线版")
        self.resize(1300, 800)

        self.view = NodeEditorView()
        self.setCentralWidget(self.view)

        self.card_presets = {
            "触发事件": {"color": "#e74c3c", "in": 0, "out": 1},   
            "逻辑条件": {"color": "#f1c40f", "in": 1, "out": 2},   
            "数据处理": {"color": "#3498db", "in": 2, "out": 1},   
            "结果输出": {"color": "#2ecc71", "in": 1, "out": 0}    
        }

        self.create_toolbar()
        self.spawn_initial_nodes()

    def create_toolbar(self):
        toolbar = QToolBar("节点工具箱")
        toolbar.setMovable(True) 
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        for name, props in self.card_presets.items():
            action = QAction(f"➕ 添加 [{name}]", self)
            action.triggered.connect(lambda checked=False, n=name, p=props: self.add_new_node(n, p))
            toolbar.addAction(action)

        toolbar.addSeparator()
        clear_action = QAction("🗑️ 清空画布", self)
        clear_action.triggered.connect(self.view.scene.clear)
        toolbar.addAction(clear_action)

    def add_new_node(self, name, props):
        node = NodeItem(name, name, props["color"], props["in"], props["out"])
        self.view.scene.addItem(node)
        center_pos = self.view.mapToScene(self.view.viewport().rect().center())
        node.setPos(center_pos.x() - 100, center_pos.y() - 100)

    def spawn_initial_nodes(self):
        n1 = NodeItem("程序启动", "触发事件", "#e74c3c", 0, 1)
        n2 = NodeItem("数据清洗", "数据处理", "#3498db", 2, 1)
        
        self.view.scene.addItem(n1)
        self.view.scene.addItem(n2)
        n1.setPos(-150, -50)
        n2.setPos(200, -100)
        
        # 默认生成一根线，并赋予一个初始名字进行演示
        edge = EdgeItem(n1.out_ports[0], n2.in_ports[0])
        edge.edge_name = "RawData" 
        self.view.scene.addItem(edge)

if __name__ == "__main__":
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    app.exec()