# ============================================================
# ui/widgets/model_settings_dialog.py
# 模型设置对话框 — 管理 AI 供应商（添加/编辑/删除/切换）
# ============================================================

import json
import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QLineEdit, QComboBox, QSplitter, QGroupBox,
    QWidget, QFormLayout, QFileDialog, QMessageBox,
    QSpinBox, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal

from services.ai_service import ai_service
from services.logger_service import app_logger


class TestConnectionWorker(QThread):
    """后台测试连接"""
    result = Signal(bool, str)

    def __init__(self, provider_id: str, config: dict, parent=None):
        super().__init__(parent)
        self._provider_id = provider_id
        self._config = config

    def run(self):
        success, msg = ai_service.test_provider(self._provider_id, config=self._config)
        self.result.emit(success, msg)


class ModelSettingsDialog(QDialog):
    """
    模型设置对话框。

    布局:
        左侧: 供应商列表（可添加/删除）
        右侧: 选中供应商的详细配置
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🤖 模型设置")
        self.resize(880, 700)
        self.setMinimumSize(750, 560)

        self._test_worker = None
        self._providers_snapshot: dict = {}  # 编辑中的配置副本
        self._active_id: str = ""
        self._loading = False  # 防止初始加载时误触发保存

        self._setup_ui()
        self._load_data()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 顶部标题
        title = QLabel("🤖 AI 供应商与模型设置")
        title.setStyleSheet(" font-weight:bold;")
        root.addWidget(title)

        desc = QLabel("配置 AI 供应商的鉴权信息、模型和代理。全局生效，所有阶段共用。")
        desc.setStyleSheet("color:#7f8c8d;")
        root.addWidget(desc)

        # 主分割区
        splitter = QSplitter(Qt.Horizontal)

        # ===== 左侧：供应商列表 =====
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 4, 0)

        list_label = QLabel("供应商列表")
        list_label.setStyleSheet("font-weight:bold;")
        ll.addWidget(list_label)

        self._provider_list = QListWidget()
        self._provider_list.setMaximumWidth(200)
        self._provider_list.setStyleSheet(
            "QListWidget{border:1px solid #dcdde1;border-radius:4px;}"
            "QListWidget::item{padding:6px 8px;}"
            "QListWidget::item:selected{background:#3498db;color:white;}"
        )
        self._provider_list.currentRowChanged.connect(self._on_provider_selected)
        ll.addWidget(self._provider_list, 1)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ 添加")
        btn_add.setFixedHeight(28)
        btn_add.clicked.connect(self._on_add_provider)
        btn_row.addWidget(btn_add)
        self._btn_delete = QPushButton("- 删除")
        self._btn_delete.setFixedHeight(28)
        self._btn_delete.clicked.connect(self._on_delete_provider)
        btn_row.addWidget(self._btn_delete)
        ll.addLayout(btn_row)

        splitter.addWidget(left)

        # ===== 右侧：配置区（带滚动） =====
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)
        rl.setSpacing(8)

        # 基本信息
        basic_group = QGroupBox("基本信息")
        basic_form = QFormLayout(basic_group)
        basic_form.setSpacing(6)

        self._edit_name = QLineEdit()
        self._edit_name.setMinimumHeight(30)
        self._edit_name.setPlaceholderText("如：Vertex AI (默认)")
        basic_form.addRow("名称:", self._edit_name)

        self._combo_type = QComboBox()
        self._combo_type.setMinimumHeight(30)
        self._combo_type.addItems(["Vertex AI", "OpenAI 兼容 (豆包/DeepSeek/OpenAI等)"])
        self._combo_type.currentIndexChanged.connect(self._on_type_changed)
        basic_form.addRow("类型:", self._combo_type)

        rl.addWidget(basic_group)

        # 鉴权区（根据类型 show/hide）
        auth_group = QGroupBox("鉴权设置")
        auth_form = QFormLayout(auth_group)
        auth_form.setSpacing(6)

        # --- Vertex 鉴权字段 ---
        self._vertex_widgets = []  # 用于批量 show/hide

        key_row = QHBoxLayout()
        self._edit_key_path = QLineEdit()
        self._edit_key_path.setMinimumHeight(30)
        self._edit_key_path.setPlaceholderText("JSON 服务账号密钥文件路径")
        key_row.addWidget(self._edit_key_path, 1)
        self._btn_browse = QPushButton("浏览...")
        self._btn_browse.setFixedWidth(60)
        self._btn_browse.clicked.connect(self._on_browse_key)
        key_row.addWidget(self._btn_browse)

        self._lbl_key = QLabel("密钥文件:")
        auth_form.addRow(self._lbl_key, key_row)
        self._vertex_widgets.extend([self._lbl_key, self._edit_key_path, self._btn_browse])

        vertex_hint = QLabel("⚠️ 目前仅支持 JSON 服务账号密钥文件鉴权")
        vertex_hint.setStyleSheet("color:#e67e22;")
        auth_form.addRow("", vertex_hint)
        self._vertex_widgets.append(vertex_hint)

        self._edit_project_id = QLineEdit()
        self._edit_project_id.setMinimumHeight(30)
        self._edit_project_id.setPlaceholderText("GCP 项目 ID")
        self._lbl_proj = QLabel("Project ID:")
        auth_form.addRow(self._lbl_proj, self._edit_project_id)
        self._vertex_widgets.extend([self._lbl_proj, self._edit_project_id])

        self._edit_location = QLineEdit()
        self._edit_location.setMinimumHeight(30)
        self._edit_location.setPlaceholderText("如 us-central1")
        self._edit_location.setText("us-central1")
        self._lbl_loc = QLabel("Location:")
        auth_form.addRow(self._lbl_loc, self._edit_location)
        self._vertex_widgets.extend([self._lbl_loc, self._edit_location])

        # --- OpenAI 兼容鉴权字段 ---
        self._openai_widgets = []

        self._edit_api_key = QLineEdit()
        self._edit_api_key.setMinimumHeight(30)
        self._edit_api_key.setPlaceholderText("API Key (sk-xxx)")
        self._edit_api_key.setEchoMode(QLineEdit.Password)
        self._lbl_apikey = QLabel("API Key:")
        auth_form.addRow(self._lbl_apikey, self._edit_api_key)
        self._openai_widgets.extend([self._lbl_apikey, self._edit_api_key])

        self._edit_base_url = QLineEdit()
        self._edit_base_url.setMinimumHeight(30)
        self._edit_base_url.setPlaceholderText("如 https://ark.cn-beijing.volces.com/api/v3")
        self._lbl_baseurl = QLabel("Base URL:")
        auth_form.addRow(self._lbl_baseurl, self._edit_base_url)
        self._openai_widgets.extend([self._lbl_baseurl, self._edit_base_url])

        rl.addWidget(auth_group)

        # 模型设置
        model_group = QGroupBox("模型设置")
        mf = QFormLayout(model_group)
        mf.setSpacing(6)

        self._combo_model = QComboBox()
        self._combo_model.setMinimumHeight(30)
        self._combo_model.setEditable(True)
        self._combo_model.setInsertPolicy(QComboBox.NoInsert)
        mf.addRow("当前模型:", self._combo_model)

        models_row = QHBoxLayout()
        self._edit_models = QLineEdit()
        self._edit_models.setMinimumHeight(30)
        self._edit_models.setPlaceholderText("可用模型列表，逗号分隔")
        models_row.addWidget(self._edit_models, 1)
        mf.addRow("可用模型:", models_row)

        rl.addWidget(model_group)

        # Embedding 设置
        emb_group = QGroupBox("Embedding 设置 (RAG 向量检索)")
        ef = QFormLayout(emb_group)
        ef.setSpacing(6)

        self._edit_emb_model = QLineEdit()
        self._edit_emb_model.setMinimumHeight(30)
        self._edit_emb_model.setPlaceholderText("留空 = 不支持 Embedding，RAG 将自动跳过")
        ef.addRow("Embedding 模型:", self._edit_emb_model)

        self._spin_emb_dim = QSpinBox()
        self._spin_emb_dim.setMinimumHeight(30)
        self._spin_emb_dim.setRange(0, 4096)
        self._spin_emb_dim.setValue(768)
        ef.addRow("向量维度:", self._spin_emb_dim)

        rl.addWidget(emb_group)

        # 网络设置
        net_group = QGroupBox("网络设置")
        nf = QFormLayout(net_group)
        nf.setSpacing(6)

        self._edit_proxy = QLineEdit()
        self._edit_proxy.setMinimumHeight(30)
        self._edit_proxy.setPlaceholderText("代理地址，留空则不使用代理")
        nf.addRow("代理:", self._edit_proxy)

        rl.addWidget(net_group)

        # 测试连接
        test_row = QHBoxLayout()
        self._btn_test = QPushButton("🔗 测试连接")
        self._btn_test.setFixedHeight(32)
        self._btn_test.setStyleSheet(
            "QPushButton{background:#3498db;color:white;border:none;"
            "border-radius:4px;padding:4px 16px;font-weight:bold;}"
            "QPushButton:hover{background:#2980b9;}"
            "QPushButton:disabled{background:#bdc3c7;}"
        )
        self._btn_test.clicked.connect(self._on_test_connection)
        test_row.addWidget(self._btn_test)

        self._test_status = QLabel("")
        self._test_status.setStyleSheet("")
        self._test_status.setWordWrap(True)
        test_row.addWidget(self._test_status, 1)
        rl.addLayout(test_row)

        rl.addStretch()

        scroll.setWidget(right)
        splitter.addWidget(scroll)
        splitter.setSizes([180, 650])

        root.addWidget(splitter, 1)

        # 底部按钮
        bottom = QHBoxLayout()

        self._btn_set_default = QPushButton("⭐ 设为默认")
        self._btn_set_default.setStyleSheet(
            "QPushButton{background:#e67e22;color:white;border:none;"
            "border-radius:4px;padding:6px 14px;font-weight:bold;}"
            "QPushButton:hover{background:#d35400;}"
        )
        self._btn_set_default.clicked.connect(self._on_set_default)
        bottom.addWidget(self._btn_set_default)

        bottom.addStretch()

        btn_ok = QPushButton("确定")
        btn_ok.setFixedWidth(80)
        btn_ok.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;border:none;"
            "border-radius:4px;padding:6px 14px;font-weight:bold;}"
            "QPushButton:hover{background:#229954;}"
        )
        btn_ok.clicked.connect(self._on_ok)
        bottom.addWidget(btn_ok)

        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedWidth(80)
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_cancel)

        root.addLayout(bottom)

    # ------------------------------------------------------------------ #
    # 数据加载
    # ------------------------------------------------------------------ #
    def _load_data(self):
        self._loading = True
        ai_service.initialize()
        self._providers_snapshot = {}
        for pid, cfg in ai_service.get_all_providers().items():
            self._providers_snapshot[pid] = dict(cfg)
        self._active_id = ai_service.get_active_provider_id()

        self._refresh_list()
        self._loading = False

    def _refresh_list(self):
        self._provider_list.blockSignals(True)
        self._provider_list.clear()
        for pid, cfg in self._providers_snapshot.items():
            name = cfg.get("name", pid)
            prefix = "⭐ " if pid == self._active_id else "    "
            item = QListWidgetItem(f"{prefix}{name}")
            item.setData(Qt.UserRole, pid)
            self._provider_list.addItem(item)
        self._provider_list.blockSignals(False)

        if self._provider_list.count() > 0:
            self._provider_list.setCurrentRow(0)

    # ------------------------------------------------------------------ #
    # 供应商选择
    # ------------------------------------------------------------------ #
    def _on_provider_selected(self, row: int):
        if row < 0:
            return
        # B3 修复：切换前先保存当前编辑（跳过初始加载阶段）
        if not self._loading:
            self._save_current_to_snapshot()
        item = self._provider_list.item(row)
        if not item:
            return
        pid = item.data(Qt.UserRole)
        cfg = self._providers_snapshot.get(pid, {})
        self._fill_form(cfg)

    def _fill_form(self, cfg: dict):
        self._edit_name.setText(cfg.get("name", ""))
        ptype = cfg.get("type", "vertex")
        type_idx = 0 if ptype == "vertex" else 1
        self._combo_type.setCurrentIndex(type_idx)
        self._on_type_changed(type_idx)  # 确保 show/hide 刷新

        # Vertex
        self._edit_key_path.setText(cfg.get("key_path", ""))
        self._edit_project_id.setText(cfg.get("project_id", ""))
        self._edit_location.setText(cfg.get("location", "us-central1"))

        # OpenAI
        self._edit_api_key.setText(cfg.get("api_key", ""))
        self._edit_base_url.setText(cfg.get("base_url", ""))

        # 模型
        models = cfg.get("models", [])
        self._combo_model.clear()
        self._combo_model.addItems(models)
        current_model = cfg.get("model", "")
        idx = self._combo_model.findText(current_model)
        if idx >= 0:
            self._combo_model.setCurrentIndex(idx)
        else:
            self._combo_model.setCurrentText(current_model)
        self._edit_models.setText(", ".join(models))

        # Embedding
        self._edit_emb_model.setText(cfg.get("embedding_model", ""))
        self._spin_emb_dim.setValue(cfg.get("embedding_dim", 768))

        # 网络
        self._edit_proxy.setText(cfg.get("proxy", ""))

        self._test_status.clear()

    def _on_type_changed(self, index: int):
        is_vertex = (index == 0)
        for w in self._vertex_widgets:
            w.setVisible(is_vertex)
        for w in self._openai_widgets:
            w.setVisible(not is_vertex)

    def _on_browse_key(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择 JSON 密钥文件", "",
            "JSON Files (*.json);;All Files (*)",
        )
        if filepath:
            self._edit_key_path.setText(filepath)

    # ------------------------------------------------------------------ #
    # 读取表单
    # ------------------------------------------------------------------ #
    def _read_form(self) -> dict:
        is_vertex = self._combo_type.currentIndex() == 0
        models_text = self._edit_models.text().strip()
        models = [m.strip() for m in models_text.split(",") if m.strip()]

        cfg = {
            "type": "vertex" if is_vertex else "openai_compatible",
            "name": self._edit_name.text().strip() or "未命名",
            "model": self._combo_model.currentText().strip(),
            "models": models,
            "embedding_model": self._edit_emb_model.text().strip(),
            "embedding_dim": self._spin_emb_dim.value(),
            "proxy": self._edit_proxy.text().strip(),
        }

        if is_vertex:
            cfg["key_path"] = self._edit_key_path.text().strip()
            cfg["project_id"] = self._edit_project_id.text().strip()
            cfg["location"] = self._edit_location.text().strip() or "us-central1"
        else:
            cfg["api_key"] = self._edit_api_key.text().strip()
            cfg["base_url"] = self._edit_base_url.text().strip()

        return cfg

    def _save_current_to_snapshot(self):
        """将当前表单内容保存回 snapshot"""
        row = self._provider_list.currentRow()
        if row < 0:
            return
        item = self._provider_list.item(row)
        if not item:
            return
        pid = item.data(Qt.UserRole)
        self._providers_snapshot[pid] = self._read_form()

    # ------------------------------------------------------------------ #
    # 添加/删除
    # ------------------------------------------------------------------ #
    def _on_add_provider(self):
        # 生成唯一 ID
        idx = len(self._providers_snapshot) + 1
        while f"provider_{idx}" in self._providers_snapshot:
            idx += 1
        pid = f"provider_{idx}"

        cfg = {
            "type": "openai_compatible",
            "name": f"新供应商 {idx}",
            "api_key": "",
            "base_url": "",
            "model": "",
            "models": [],
            "embedding_model": "",
            "embedding_dim": 0,
            "proxy": "",
        }
        self._providers_snapshot[pid] = cfg
        self._refresh_list()
        # 选中最后一个
        self._provider_list.setCurrentRow(self._provider_list.count() - 1)

    def _on_delete_provider(self):
        row = self._provider_list.currentRow()
        if row < 0:
            return
        item = self._provider_list.item(row)
        pid = item.data(Qt.UserRole)

        if len(self._providers_snapshot) <= 1:
            QMessageBox.warning(self, "提示", "至少保留一个供应商。")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除供应商「{self._providers_snapshot[pid].get('name', pid)}」？",
        )
        if reply == QMessageBox.Yes:
            del self._providers_snapshot[pid]
            if self._active_id == pid:
                self._active_id = next(iter(self._providers_snapshot))
            self._refresh_list()

    # ------------------------------------------------------------------ #
    # 设为默认 / 测试连接
    # ------------------------------------------------------------------ #
    def _on_set_default(self):
        row = self._provider_list.currentRow()
        if row < 0:
            return
        item = self._provider_list.item(row)
        pid = item.data(Qt.UserRole)
        self._active_id = pid
        self._refresh_list()
        self._provider_list.setCurrentRow(row)
        QMessageBox.information(
            self, "设为默认",
            f"已将「{self._providers_snapshot[pid].get('name', pid)}」设为默认供应商。",
        )

    def _on_test_connection(self):
        self._save_current_to_snapshot()
        row = self._provider_list.currentRow()
        if row < 0:
            return
        item = self._provider_list.item(row)
        pid = item.data(Qt.UserRole)
        cfg = self._providers_snapshot[pid]

        # B2 修复：直接传配置测试，不先写入全局状态
        self._btn_test.setEnabled(False)
        self._test_status.setText("⏳ 正在测试连接...")
        self._test_status.setStyleSheet(" color:#e67e22;")

        self._test_worker = TestConnectionWorker(pid, config=cfg, parent=self)
        self._test_worker.result.connect(self._on_test_result)
        self._test_worker.start()

    def _on_test_result(self, success: bool, msg: str):
        self._btn_test.setEnabled(True)
        if success:
            self._test_status.setText(msg)
            self._test_status.setStyleSheet(" color:#27ae60; font-weight:bold;")
        else:
            self._test_status.setText(msg)
            self._test_status.setStyleSheet(" color:#e74c3c;")

    # ------------------------------------------------------------------ #
    # 确定/取消
    # ------------------------------------------------------------------ #
    def _on_ok(self):
        self._save_current_to_snapshot()

        # 保存所有供应商到 ai_service
        existing = set(ai_service.get_all_providers().keys())
        new_ids = set(self._providers_snapshot.keys())

        # 删除被移除的
        for pid in existing - new_ids:
            ai_service.remove_provider(pid)

        # 添加/更新
        for pid, cfg in self._providers_snapshot.items():
            if pid in existing:
                ai_service.update_provider(pid, cfg)
            else:
                ai_service.add_provider(pid, cfg)

        # B1 修复：切换供应商时包 try/except，延迟到实际调用时再初始化
        try:
            ai_service.switch_provider(self._active_id)
        except Exception as e:
            # 切换失败（如配置不完整），仅保存配置不初始化
            ai_service._active_id = self._active_id
            ai_service._save_config()
            QMessageBox.warning(
                self, "提示",
                f"供应商配置已保存，但初始化失败：\n{str(e)}\n\n"
                f"请检查配置后重试。程序将在下次 AI 调用时重新尝试初始化。",
            )

        # P4 提示：检查 Embedding 维度一致性
        emb_dims = set()
        for pid, cfg in self._providers_snapshot.items():
            if cfg.get("embedding_model"):
                emb_dims.add(cfg.get("embedding_dim", 768))
        if len(emb_dims) > 1:
            QMessageBox.warning(
                self, "Embedding 维度警告",
                f"检测到多个供应商的 Embedding 维度不一致（{emb_dims}）。\n\n"
                f"如果在同一个项目中切换供应商，RAG 向量索引可能崩溃。\n"
                f"建议：同一项目全程使用同系列的 Embedding 模型（如始终用 Google 或始终用豆包）。",
            )

        app_logger.info(
            "模型设置",
            f"保存供应商配置: {len(self._providers_snapshot)} 个供应商, "
            f"默认: {self._providers_snapshot.get(self._active_id, {}).get('name', self._active_id)}",
        )
        self.accept()
