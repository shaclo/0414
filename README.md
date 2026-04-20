# AI 短剧剧本生成系统

基于 Gemini 2.5 Flash + PySide6 的多阶段 AI 剧本创作工具。

---

## 环境要求

- Windows 10/11（x64 或 ARM64）
- Python 3.11+
- 本地代理（默认 `127.0.0.1:7897`，用于访问 Vertex AI）

---

## 安装步骤

```bat
:: 1. 创建虚拟环境
python -m venv .venv

:: 2. 激活
.venv\Scripts\activate

:: 3. 安装依赖
pip install -r requirements.txt
```

---

## 配置 Vertex AI 密钥

1. 前往 [Google Cloud Console](https://console.cloud.google.com/) → IAM → 服务账号
2. 为项目 `gen-lang-client-xxxxxxxx` 下载 JSON 格式的服务账号密钥
3. 将下载的 `.json` 文件放入项目根目录的 `key/` 文件夹

   ```
   key/
   └── your-project-xxxxx.json   ← 放这里
   ```

4. 打开 `proxyserverconfig.py`，按实际情况修改：

   ```python
   VERTEX_PROJECT_ID = "your-project-id"
   VERTEX_LOCATION   = "us-central1"
   VERTEX_KEY_PATH   = "key/your-project-xxxxx.json"
   PROXY_HOST        = "127.0.0.1"   # 本地代理地址
   PROXY_PORT        = 7897          # 本地代理端口
   ```

---

## 启动

```bat
.venv\Scripts\activate
python main.py
```

---

## 操作流程

整个创作过程分为 6 个阶段，按顺序推进：

### 第 1 阶段 · 创世
1. 在输入框中填写**一句话梗概**（Sparkle）
2. 点击「AI 追问」→ 系统生成 5~8 个关键追问
3. 逐一回答追问，点击「锁定世界观」→ AI 提炼世界观变量表

### 第 2 阶段 · 人物
1. 点击「🤖 AI 建议角色」，设定数量后生成角色阵容
2. 在右侧编辑每个角色的属性（性格、动机、外貌等）
3. 在人物关系表中添加角色之间的关系
4. 点击「确认人物设定，进入骨架」

### 第 3 阶段 · 骨架
1. 设定总集数和每集时长，点击「生成 CPG 骨架」
2. 在图中**拖动节点**调整布局；**从节点右侧端口拖线**到另一节点左侧端口创建连线
3. **双击连线**可修改因果关系类型（直接因果 / 情感驱动 / 并行主题等）
4. 点击节点可修改标题；通过「编号」下拉框可调整节点剧情顺序
5. 点击「进入血肉阶段」（系统会自动检测节点编号冲突）

### 第 4 阶段 · 血肉
1. 选择参与生成的 AI 人格（可多选），调整 AI 参数
2. 点击「开始生成变体」→ 各人格并行生成当前节点的 Story Beat
3. 点击左侧卡片查看各方案，可在右侧直接编辑内容，点「💾 保存修改」
4. 选定满意的方案后点「确认此 Beat」，自动跳转下一节点
5. 也可点「🚀 一键批量生成」连续生成后续多个章节（需逐一确认）

### 第 5 阶段 · 扩写
1. 所有节点确认后进入扩写阶段
2. AI 将 Story Beat 扩写为标准短剧剧本格式
3. 可在编辑框内进一步修改，满意后锁定

### 第 6 阶段 · 锁定
- 查看最终剧本，支持导出保存

---

## 系统更新

通过菜单栏 **系统 → 系统更新** 可检查并下载最新版本：

1. 点击「检查更新」→ 自动对比 GitHub Release 版本号
2. 发现新版本 → 右侧显示更新日志 → 点击「下载并更新」
3. 进度条实时显示下载/解压进度
4. 更新完成后弹出提示，手动关闭并重启软件即可

---

## 项目目录结构

```
0414/
├── main.py                          # 应用入口，初始化 QApplication 和全局样式
├── env.py                           # 所有 AI Prompt 模板 + 系统版本信息 + GitHub 更新配置
├── proxyserverconfig.py             # Vertex AI 密钥路径、代理地址、项目 ID 配置
├── requirements.txt                 # Python 依赖列表
├── README.md                        # 项目说明文档
│
├── key/                             # Vertex AI 服务账号密钥（不提交到 Git）
│   └── *.json                       # Google Cloud 服务账号 JSON 密钥文件
│
├── config/                          # 配置与模板数据
│   ├── prompt_templates.py          # 爽感/钩子公式管理器（采样、按ID构建、按集号调度）
│   ├── prompt_templates.json        # 爽感公式 & 钩子公式的数据存储（JSON）
│   ├── bvsr_personas.json           # BVSR 多人格定义（性格、风格、写作倾向）
│   └── genre_presets.json           # 题材预设（犯罪/爱情/悬疑/复仇等风格参数）
│
├── models/                          # 数据模型层
│   ├── data_models.py               # 核心数据结构（节点、边、角色、世界观变量等）
│   └── project_state.py             # 项目全局状态（阶段数据、AI参数、爽感间隔等）
│
├── services/                        # 业务逻辑层
│   ├── ai_service.py                # Vertex AI / Gemini API 封装（流式生成、重试）
│   ├── worker.py                    # 多线程 Worker（骨架生成、血肉变体、扩写、级联重写）
│   ├── persona_engine.py            # BVSR 人格引擎（加载/激活/注入人格到 Prompt）
│   ├── genre_manager.py             # 题材预设管理（加载/切换/注入题材风格）
│   ├── rag_controller.py            # RAG 向量检索控制器（FAISS 本地向量库）
│   ├── ite_calculator.py            # ITE 因果效应计算器（节点间因果强度评估）
│   └── updater.py                   # GitHub Release 自动更新（检查/下载/解压）
│
├── ui/                              # 界面层
│   ├── main_window.py               # 主窗口（菜单栏、导航栏、Phase 切换、文件管理）
│   ├── phase1_genesis.py            # 第1阶段 · 创世（一句话梗概 → 苏格拉底盘问 → 世界观）
│   ├── phase2_characters.py         # 第2阶段 · 人物（AI角色建议 → 编辑属性 → 人物关系）
│   ├── phase2_skeleton.py           # 第3阶段 · 骨架（CPG 因果图生成 → 节点编排 → 连线）
│   ├── phase3_flesh.py              # 第4阶段 · 血肉（BVSR 多人格并行生成 Story Beat）
│   ├── phase5_expansion.py          # 第5阶段 · 扩写（Beat → 标准剧本，爽感/钩子/时长控制）
│   ├── phase4_lock.py               # 第6阶段 · 锁定（最终剧本查看与导出）
│   │
│   └── widgets/                     # 可复用 UI 组件
│       ├── ai_settings_panel.py     # AI 参数面板（温度/模型选择）
│       ├── beat_card.py             # Beat 卡片（血肉阶段的变体方案展示）
│       ├── bvsr_settings_dialog.py  # BVSR 人格管理对话框（增删改查人格）
│       ├── cascade_rewrite_dialog.py# 级联重写对话框（修改一处自动更新下游）
│       ├── character_editor.py      # 角色属性编辑器（姓名/性别/性格/动机等）
│       ├── character_graph_widget.py# 人物关系力导向图（可视化角色关系网络）
│       ├── character_relation_panel.py # 人物关系表格面板（添加/编辑/删除关系）
│       ├── cpg_graph_editor.py      # CPG 因果图编辑器（拖拽节点、连线、编号）
│       ├── genre_settings_dialog.py # 题材预设对话框（查看/切换写作风格）
│       ├── node_detail_dialog.py    # 节点详情对话框（编辑标题/Beat/设定/角色）
│       ├── persona_selector.py      # 人格选择器（多选参与生成的 AI 人格）
│       ├── prompt_template_dialog.py# 爽感&钩子公式管理对话框（启用/禁用/编辑公式）
│       ├── prompt_viewer.py         # Prompt 实时预览面板（查看当前注入的完整 Prompt）
│       ├── qa_panel.py              # 问答面板（苏格拉底盘问的追问与回答）
│       ├── range_slider.py          # 双端滑块（时长区间选择器）
│       ├── screenplay_editor.py     # 剧本编辑器（字数统计、目标提示、实时编辑）
│       ├── skeleton_ai_settings_dialog.py # 骨架 AI 辅助修改对话框（方向/微调/模板）
│       ├── split_dialog.py          # 节点拆分对话框（一个 Beat 拆为多集）
│       └── world_var_table.py       # 世界观变量表（展示 AI 提炼的世界观键值对）
│
├── projects/                        # 项目存档目录（JSON 格式，自动保存）
├── vector_db/                       # RAG 本地 FAISS 向量库缓存
└── examplepaper/                    # 示例论文/参考资料
```

---

## 更新日志

### v1.1.2（2026-04-20）— 当前版本
- **系统更新模块**：左右分栏对话框（左侧版本信息+操作，右侧更新日志）
- **版本号自动写入**：更新成功后自动将新版本号写入 `env.py`
- **更新提示优化**：更新完成后弹出警告框提示手动重启

### v1.1.0（2026-04-20）`de43103`
- **爽感写作铁律**：System Prompt 永久注入「铺垫压迫 → 反差释放 → 旁观者放大」三段式技法
- **钩子写作铁律**：System Prompt 永久注入「中断不是结束」写作原则 + 5 条伪钩子禁止令
- **爽感节奏调度**：按集号自动调度小爽/中爽/大爽等级（可配置间隔参数）
- **爽感/钩子公式管理**：新增 `prompt_templates.json` + 管理对话框（启用/禁用/编辑公式）
- **扩写 UI 增强**：左侧滚动面板、公式多选、时长区间双端滑块、字数目标联动
- **系统更新模块**：从 GitHub Release 检查/下载/解压更新 + 进度条
- **工具/系统菜单拆分**：「工具」菜单管理创作设置，「系统」菜单管理版本更新

### v1.0.1（2026-04-18）`00870d3`
- **级联重写引擎**：修改一个节点后自动更新所有下游节点的 Story Beat
- **骨架 AI 辅助修改**：新增情节方向、结构微调的 Prompt 模板管理对话框
- **扩写修正**：修复拆分后扩写、自动扩写的状态同步问题
- **人物关系图优化**：修复力导向图的节点拖拽和布局稳定性

### v1.0.0（2026-04-18）`785a640`
- **人物关系力导向图**：可视化角色关系网络，支持拖拽交互
- **节点详情对话框**：双击节点打开完整编辑面板（标题/Beat/设定/角色/因果关系）
- **节点拆分功能**：一个 Story Beat 可拆分为多集
- **题材预设系统**：犯罪/爱情/悬疑/复仇等风格参数管理
- **BVSR 人格选择器重构**：支持多选人格并行生成
- **Prompt 体系扩展**：新增级联重写、骨架修改、扩写等多套 Prompt 模板

### v0.3.0（2026-04-17）`2d6b86f`
- **BVSR 多人格系统**：加入人格定义（性格/风格/写作倾向），支持增删改查
- **BVSR 设置对话框**：通过菜单管理人格配置
- **扩写阶段增强**：扩写 Worker 支持多人格注入
- **角色编辑器优化**：扩展角色属性编辑面板

### v0.2.0（2026-04-15）`6be43dc`
- **第一个完整功能版本**：6 个阶段全部可用
- **CPG 因果图编辑器**：拖拽节点、连线、编号、双击编辑因果关系类型
- **人物关系表格**：添加/编辑/删除角色关系
- **苏格拉底盘问面板**：追问与回答的交互流程完善
- **主窗口框架**：菜单栏、导航栏、Phase 切换、文件保存/加载
- **README 文档**：首次编写项目说明

### v0.1.1（2026-04-15）`5748f11`
- **AI 服务层重构**：Vertex AI 流式生成封装、重试机制
- **骨架阶段扩展**：节点编排逻辑、因果连线基础功能
- **血肉阶段扩展**：变体生成 Worker、Beat 确认流程
- **AI 设置面板**：温度/模型选择控件

### v0.1.0（2026-04-15）`29d48fe`
- **项目初始化**：基础框架搭建
- **6 阶段架构设计**：创世 → 人物 → 骨架 → 血肉 → 扩写 → 锁定
- **AI 调用基础**：Vertex AI 代理配置、基本 Prompt 模板
- **数据模型**：节点、边、角色、项目状态等核心数据结构

---

> ⚠️ `key/` 目录已加入 `.gitignore`，请勿手动提交密钥文件。
