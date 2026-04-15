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

## 文件说明

| 文件/目录 | 说明 |
|-----------|------|
| `key/` | Vertex AI 服务账号密钥（**不要提交到 Git**） |
| `proxyserverconfig.py` | 代理和 AI 配置 |
| `env.py` | 所有 AI Prompt 模板 |
| `projects/` | 项目存档（JSON 格式自动保存） |
| `vector_db/` | RAG 本地向量库缓存 |

---

> ⚠️ `key/` 目录已加入 `.gitignore`，请勿手动提交密钥文件。
