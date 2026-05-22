# HTN_webUI

这是一个本地运行的 Streamlit 原型，支持：

- 上传图片并拆解物件 list
- 拆解模型可选：Gemini/Banana、OpenAI Vision、Claude Vision、Ensemble 多模型合并、Mock
- 生成单物件三视图
- 素材入库
- 选择素材组合生成概念图（未实装）
- 上传草图并细化（未实装）
- 图像生成模型可选：Gemini/Banana、OpenAI （暂时仅支持官方API）

## 1. 安装
release 最新版本直接下载并解压

## 2. 启动
- 点击 点此安装依赖.bat
- 点击 点此运行.bat

# 更新日志
## v1.1：提示词设置页

新增顶部 Tab：`设置`。

可在里面编辑并保存以下步骤的提示词：

- 流 A：拆解 list / 物件识别
- 流 A：三视图生成
- 流 B：组合生成 / 环境调整
- 流 C：草图细化

提示词保存位置：

```text
data/prompt_settings.json
```

可用变量：

```text
三视图生成：{{object_name}}、{{object_description}}
组合生成：{{composition_prompt}}、{{time}}、{{lighting}}、{{weather}}、{{style}}、{{camera}}
草图细化：{{refine_prompt}}
```

保存后下一次执行对应任务会自动使用新提示词。

## v1.2：界面调整与 API 输入栏

新增内容：

- 移除页面上方大标题，界面更紧凑。
- 左侧栏模型选择下方增加 API Key 输入栏。
- API Key 和模型名称可保存到：

```text
data/app_config.json
```

- 顶部不再单独展示「素材仓库」Tab。
- 素材仓库移动到页面底部，作为类似 Unity 资产管理器的下边栏。
- 底部素材仓库支持分类筛选、搜索、重命名、删除。

说明：`data/app_config.json` 会以明文保存 API Key，仅建议本地原型阶段使用。正式部署时建议改用环境变量或密钥管理服务。

## v1.3 更新

- 左侧 Streamlit 抽拉栏改为“素材仓库”。
- 原模型选择、API Key、模型名称设置移入“设置 → 模型 / API”。
- 提示词仍在“设置 → 提示词”。
- 删除底部素材仓库，避免页面过长。
- 新版 `run_webui.bat` 会显示运行日志，并把错误写入 `run_webui_log.txt`。

### 一键启动

双击项目根目录下的：

```bat
run_webui.bat
```

如果窗口仍然一闪而过，请用 CMD 进入项目目录后运行：

```bat
run_webui.bat
```

并把 `run_webui_log.txt` 的内容发出来排查。

## v1.4 更新

- 左侧素材仓库改为可折叠分类菜单。
- 支持在素材仓库中移动素材分类；如果安装了 `streamlit-sortables`，可以使用拖拽分类。
- 生成结果不再自动入库。
- 新增“生成结果”分栏，每张图都会保存对应提示词。
- 每个生成结果支持“入库 / 保存信息 / 删除”。
- 生成结果保存到 `data/generation_results.json`。

启动建议使用：

```bat
start_webui.bat
```

如果新增依赖没有安装，运行：

```bat
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## v1.5 更新

- 物件选择改为只支持同时选择 1 个物件。
- 加入清空所有结果。
- 加入复制信息到剪贴板功能。
- 入库加入二次确认，二次确认时可以选择入库分类。
- 仓库加入 新建分类 删除分类。
- 优化默认提示词逻辑。
- 加入素材检索功能、方便通过素材名、分类名或 ID 定位。
- 将分类管理从左侧侧栏移出。
- 优化上传图片，加入去重逻辑。
