# Snowboard Vision Data Platform：Gold Labels 团队交接与执行手册

> 文档用途：Victoria 可以把本文件直接交给协作成员。两个人按本文分工完成原始视频 PII gold labels、脱敏视频 residual-PII gold labels、交叉审核和最终评估。  
> 项目仓库：`Victoria824/SkateboardCoaching`  
> 当前工作分支：`codex/review-dataset-health`  
> 标注规范版本：`1.0`  
> 安全原则：原始 PII 视频、正例泄漏控制视频、抽帧图片和未脱敏标注不得提交到 GitHub，也不得发送到公开网盘。

## 1. 先了解这个项目

### 1.1 项目是什么

Snowboard Vision Data Platform 是一个面向真实视频的计算机视觉数据平台。它不是单纯调用
AI 生成滑雪建议的 demo，而是覆盖机器学习数据生产完整链路：

```text
视频采集 / 上传
      ↓
FFmpeg 元数据读取和抽帧
      ↓
本地 CV 模型推理
      ↓
浏览器标注：框、关键点、多边形、像素 mask
      ↓
模型预测的接受 / 修正 / 拒绝
      ↓
跟踪、传播、复核队列、数据健康指标
      ↓
PII 人脸 / 车牌 / 屏幕审核和脱敏
      ↓
独立二次模型检查 residual PII
      ↓
COCO / YOLO / sanitized bundle / 审计 manifest
```

主系统由 React/TypeScript、FastAPI、SQLAlchemy、PostgreSQL/SQLite、FFmpeg、Ultralytics、
OpenCV、Grounding DINO、Redis/Celery 和 S3/MinIO 组成。`server/` 下的 Node/Replicate
滑雪教练是 legacy 下游 demo，不是 gold labels 或隐私决策的数据源。

### 1.2 为什么需要 gold labels

模型输出数量不能证明准确率。只有经过人工标注、独立复核、冻结版本的 gold dataset
才能测量：

- precision、recall、F1、F2 和 IoU；
- 每分钟漏检数量；
- 含 PII 帧的漏检比例；
- 人脸、车牌、屏幕各类别表现；
- 低光、运动模糊、小目标、遮挡等困难场景表现；
- 同一目标跨帧覆盖率；
- 脱敏后仍然可辨认的 residual PII 漏检率。

本项目需要两套互相独立的 gold labels：

| 数据集 | 标注对象 | 输入 | 用途 |
| --- | --- | --- | --- |
| Original PII Gold | 原始画面中的全部人脸、车牌、屏幕 | 原始视频 5 FPS 帧 | 测首检 OpenCV/YOLO 的 recall/precision |
| Residual PII Gold | 脱敏后仍然可辨认的 PII | sanitized 视频 5 FPS 帧 | 测独立 Grounding DINO 二检的漏检率 |

两套数据不能混用。原始视频中的人脸不等于脱敏后仍泄漏的人脸。

## 2. 最终要交付什么

团队完成后，以下文件必须齐全：

```text
private-gold-workspace/                   # 私有目录，不提交 Git
├── sources/
│   ├── originals/                       # 获得授权的原始视频
│   ├── sanitized-clean/                  # 正常脱敏输出
│   └── residual-positive-controls/       # 故意保留少量泄漏的测试副本，永不交付客户
├── permission-evidence/                  # 授权说明、拍摄同意、来源页面截图
├── reports/
│   ├── original-pii-*.json               # 首检预测报告
│   └── residual-pii-*.json               # 独立二检预测报告
├── manifests/
│   ├── original_pii_gold_manifest.json
│   └── residual_pii_gold_manifest.json
├── metrics/
│   ├── original_pii_gold_metrics.json
│   └── residual_pii_gold_metrics.json
└── qa/
    ├── disagreements.md
    ├── source-inventory.md
    └── final-signoff.md
```

可以提交到 GitHub 的内容只有：不含 PII 的方法文档、空模板、聚合指标和不可逆 SHA-256。
不得提交视频、抽帧图片、姓名、车牌号码、屏幕内容或 permission evidence 中的个人信息。

## 3. 两个人如何各完成一半

不要让一个人同时标注并批准自己的帧。推荐使用交叉审核：

| 工作 | Victoria | 团队成员 |
| --- | --- | --- |
| 素材收集 | 视频组 A，约 50% | 视频组 B，约 50% |
| 第一轮标注 | 标注组 A | 标注组 B |
| 第二轮审核 | 审核组 B | 审核组 A |
| 分歧处理 | 与成员共同裁决 | 与 Victoria 共同裁决 |
| Original PII 报告 | 生成组 A 预测 | 生成组 B 预测 |
| Residual positive controls | 制作组 A | 制作组 B |
| 最终 manifest | 合并、冻结版本 | 独立核对 hash、帧数和身份字段 |
| 最终 metrics | 执行评估 | 复核命令、输入 hash 和结果 |

按“视频”分组，不按相邻帧分组。相邻帧高度相似，如果一个人标奇数帧、另一个人标偶数帧，
既容易互相影响，也会造成 train/test temporal leakage。

建议在 `source-inventory.md` 使用以下表格：

| video_id | 文件名 | 类别重点 | 时长 | 来源/授权 | SHA-256 | split | 首标人 | 复核人 | 状态 |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| A01 |  | face |  |  |  | train | Victoria | Teammate | pending |
| B01 |  | plate |  |  |  | test | Teammate | Victoria | pending |

身份字段使用稳定的工作 ID，例如 `victoria`、`reviewer-b`，不要使用 `annotator-1` 后来又换人。

## 4. 素材准备

### 4.1 已有的授权起始素材

仓库本地评估目录中已有两段真实雪场视频，但原视频被 `.gitignore` 排除：

| 素材 | 作用 | SHA-256 |
| --- | --- | --- |
| [People Snowboarding At A Resort](https://www.youtube.com/watch?v=FGkxsSAJSk4)，Freestocks，Creative Commons Attribution | 拥挤场景、远距离人物、小目标、遮挡 | `8c15b3e29e864e6daed515adfddc087ff366b1a08648394642c8770a8990ac0a` |
| [Snowboarding — Free HD Royalty Stock Footage](https://www.youtube.com/watch?v=pWkGclwklFo)，Footage Island / Nissim Farin，描述允许使用并要求署名 | 单人高速动作、运动模糊、远近变化 | `a865e2270d8bf3d2e69525bf5994d10fd9dab38c845c3e903a6f36d34418f0a3` |

使用前重新检查来源页面和授权状态。网页可访问不等于允许下载、重新分发或用于公开数据集。
这两段视频可作为 snowboard 场景起点，但不足以覆盖车牌和屏幕。
团队成员 clone GitHub 仓库后不会得到这些被忽略的视频；Victoria 必须通过获授权的私有渠道交付，
或者由成员依据授权重新取得并核对相同 SHA-256。

### 4.2 还需要补充的素材

最安全的来源是团队自行拍摄、演员书面同意、使用虚构车牌和测试屏幕内容。不要拍摄真实私人聊天、
证件、银行卡、医疗信息或真实客户数据。

推荐的第一版可信 benchmark：

| 场景 | 建议视频数 | 必须覆盖 |
| --- | ---: | --- |
| 人脸 | 4–6 | 正脸、侧脸、头盔/护目镜、远距离、低光、运动模糊 |
| 车牌 | 4–6 | 正视、斜视、小目标、部分遮挡、不同光照；优先虚构/道具牌 |
| 屏幕 | 4–6 | 手机、笔记本、显示器、反光、倾斜、小屏；只显示合成内容 |
| 干净负例 | 3–4 | 无 PII 雪场、设备背面、文字标牌、板面 logo、非人脸图案 |

目标是至少 12 个视频、600 个经过双人批准的 5 FPS 帧，并尽量达到：

- `face` gold objects ≥ 200；
- `license_plate` gold objects ≥ 100；
- `screen` gold objects ≥ 100；
- 至少 20% 正例带困难场景 tag；
- 至少 20% approved frames 是真正的空负例。

这能形成可信的作品集 benchmark，但仍不是“全球生产分布”的证明。若要用零漏检样本估计漏检率上界，
可使用常见的 rule of three：零次漏检时，95% 置信上界约为 `3 / 正例数`。例如 300 个正例
只能支持“漏检率上界约 1%”，若想支持约 0.1%，需要约 3,000 个代表性正例。

### 4.3 每个素材必须保存的信息

- 原始文件名和不可修改的本地副本；
- 来源 URL 或内部拍摄编号；
- creator / 拍摄者；
- 授权或同意证据；
- 允许的用途和署名要求；
- 文件 SHA-256；
- 时长、分辨率、FPS、codec；
- 数据 split；
- 是否包含真实 PII；
- 谁可以访问以及何时删除。

macOS/Linux 计算 hash：

```bash
shasum -a 256 /path/to/video.mp4
```

如果文件发生转码、剪辑或重新下载，它就是一个新样本，必须重新计算 hash，不能沿用旧值。

## 5. 环境搭建

### 5.1 获取正确代码

```bash
git clone https://github.com/Victoria824/SkateboardCoaching.git
cd SkateboardCoaching
git switch codex/review-dataset-health
```

团队开始一批标注前，在 `source-inventory.md` 记录当前 commit：

```bash
git rev-parse HEAD
```

整个 benchmark 尽量使用同一 commit、同一 sampling profile 和同一模型配置。

### 5.2 本地模式：三个终端

首次安装：

```bash
cd media_service
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install -r requirements-ml.txt
cd ../client
npm install
```

终端 1，API：

```bash
cd media_service
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
```

终端 2，worker：

```bash
cd media_service
.venv/bin/python -m app.worker
```

终端 3，React：

```bash
cd client
REACT_APP_MEDIA_API_URL=http://localhost:8000 npm start
```

打开 `http://localhost:3000`。若使用 Docker，可运行 `docker compose up --build`，它会启动
PostgreSQL、MinIO、Redis、API、dispatcher 和两个 Celery workers。团队只需选择一种运行方式，
不要把同一批标注分散在两个不同数据库里。

### 5.3 两台电脑协作

Git 不会同步 `media_service/data/media.db`、原始视频或帧图。推荐把 API、PostgreSQL 和对象存储部署在
一个仅团队可访问的共享环境，两个人的浏览器连接同一 API。若只能各自在本机工作，则必须严格按视频
分组，各自完成自己的 task，然后分别导出 manifest 视频块再合并；不要提交或互相覆盖 `media.db`。
跨设备传输视频、数据库快照或帧图时使用加密私有渠道，并在传输后核对 SHA-256。

### 5.4 开始标注前的检查

```bash
curl http://localhost:8000/api/health
cd media_service && .venv/bin/pytest -q
```

确认系统时间正确、磁盘空间足够、浏览器缩放为 100%。先用一段不敏感的 2 秒视频跑完整流程，
再导入正式素材。

## 6. 数据集划分

### 6.1 必须按视频划分

推荐比例：

- train：60%；
- validation：20%；
- test：20%。

同一原始视频的所有帧、剪辑和近似副本必须属于同一个 split。不要把同一个人的连续动作拆进
train 和 test。最终公开的准确率只使用冻结的 `test` split；模型阈值和 prompt 调整只能看
train/validation。

### 6.2 冻结测试集

完成以下步骤后 test 才算冻结：

1. 每个 source SHA-256 已确认；
2. 每帧由一人标注、另一人审核；
3. 所有分歧已处理；
4. `review_status` 全部为 `approved`；
5. annotator 和 reviewer 不相同；
6. manifest 备份为只读副本；
7. 记录 manifest 自身的 SHA-256。

冻结后不要因为模型漏检而修改 gold。只有发现明确的人为标注错误时才能发布新 dataset version，
并记录修改原因。

## 7. Original PII Gold：原始视频标注

### 7.1 导入和抽帧

在首页选择 `Action · 5 FPS`，上传视频，等待状态变为 `READY_FOR_ANNOTATION`，然后点击
`Create annotation task` 和 `Open annotation workspace`。

为何用 5 FPS：PII 会快速进出画面，1 FPS 容易跳过短暂出现的人脸、车牌或手机。所有预测报告、
gold manifest 和 residual 扫描必须使用相同的 5 FPS 帧序号。

### 7.2 运行首检模型

在标注页点击 `PII`。模型会生成：

- `face`：OpenCV face proposal；
- `license_plate`：OpenCV plate proposal；
- `screen`：YOLO 对 TV、laptop、cell phone 的映射。

虚线琥珀色是尚未处理的模型预测：

- `A` / Accept：预测正确；
- `C` / Correct：复制后人工调整；
- `R` / Reject：误报；
- `←` / `→`：前后帧；
- `Shift + ←/→`：跳 10 帧；
- `Cmd/Ctrl + S`：保存；
- `Delete`：删除选中标注。

不要只处理模型给出的框。每帧都要从左上到右下人工扫描，补画模型完全漏掉的对象。没有 PII 的帧
也必须保存并最终批准，否则系统无法计算 false positive。

### 7.3 三个标签的定义

#### `face`

标注任何可能识别人或被人脸检测器处理的真实人脸区域：正脸、侧脸、部分遮挡、远处人脸、倒影、
屏幕中清晰显示的人脸。紧致框覆盖额头/头部上缘、下巴和左右脸部，不要把整个头盔、身体或大片背景
放进检测 gold bbox。完全不可见的后脑、纯卡通脸和不可辨认的极小噪点不标。

#### `license_plate`

标注车辆牌照的外边界，包括部分遮挡、倾斜和运动模糊但仍可判断为车牌的区域。不要标 snowboard
品牌 logo、普通道路标牌、衣服文字。正式素材优先使用虚构或经过授权的牌照。

#### `screen`

当前隐私策略保守地处理所有可见显示面：手机、平板、笔记本、显示器和 TV。框显示区域；当小手机
无法区分屏幕边缘时可框整台手机。设备背面、合上的笔记本和普通玻璃不标。屏幕中另有清晰人脸时，
同时标 `screen` 和 `face`，因为它们是两个不同检测任务。

### 7.4 Box 和 mask 不要混淆

浏览器中的 PII 接受/新画操作会生成 128×128 `row-major-rle-v1` 像素 mask，供 FFmpeg 真正
模糊视频。可以使用 `Mask +` 和 `Mask −` 修正模糊区域。

检测 gold manifest 则必须写成 `annotation_type: "bbox"`：

```json
{
  "id": "face-A01-f000123-01",
  "label": "face",
  "annotation_type": "bbox",
  "track_id": "A01-face-01",
  "geometry": {"x": 0.214, "y": 0.103, "width": 0.084, "height": 0.146}
}
```

坐标均为 0–1 归一化坐标。使用 PII mask 的 `geometry.bbox` 作为 tight detection bbox；不要把
padding 后的整个 mask 面积或 COCO 像素坐标直接复制进 detector gold。

### 7.5 框的统一标准

- 框尽量紧致，但不得切掉目标可见部分；
- 不猜测遮挡后不可见的完整形状，只框可见/可推断的外边界；
- 小目标放大检查，禁止用一个大框包多个脸或多个车牌；
- 同一对象跨帧使用同一个 `track_id`；
- 对象离开画面再返回，若能确定是同一对象，沿用 track；不能确定则新建；
- 边缘只露出一部分但仍能判定类别时应标，并加 `edge_entry`；
- 任何“是否应该标”的分歧先记入 `disagreements.md`，不要偷偷统一答案。

### 7.6 困难场景 tags

每个 frame 可以有多个 `difficult_case_tags`：

- `motion_blur`
- `low_light`
- `small_object`
- `occluded`
- `edge_entry`
- `reflection`
- `profile_face`
- `crowded`
- `screen_glare`
- `positive_control`（只用于 residual 数据）

不要给普通帧乱加 tag；无困难情况可省略或使用空数组。

### 7.7 每帧完成条件

- 所有模型预测均已 Accept、Correct 或 Reject；
- 人工扫描确认没有漏标；
- 每个框类别正确且紧致；
- 该帧所有对象已保存；
- 空帧明确保存为空；
- 跨帧 track ID 一致；
- 困难 tag 已填写；
- 标注人签名。

全部帧完成后点击 `Complete task`。完成前不要生成最终 sanitized export。

## 8. 第二人审核和分歧处理

### 8.1 审核者检查什么

审核者必须查看所有正例帧、所有空负例帧，并重点检查：

- 画面边缘、反光区域和屏幕内嵌人脸；
- 小于画面 2% 的人脸/车牌/手机；
- 连续帧中突然消失又出现的 track；
- 标为 Reject 的高置信预测；
- 空帧前后各一帧，防止短暂 PII 被跳过；
- 标签互换，例如把手机背面标成 screen；
- bbox 是否包含过多背景或切掉目标。

### 8.2 分歧记录格式

```markdown
| case_id | video | frame | object | annotator | reviewer | final decision | reason |
| --- | --- | ---: | --- | --- | --- | --- | --- |
| D-001 | A01 | 123 | edge face | label | omit | label face + edge_entry | 人类可判断为侧脸 |
```

双方先独立判断，再讨论。不要以模型输出作为裁决者。无法达成一致的样本标为 `pending`，不得进入
测试指标；必要时由第三人裁决。

### 8.3 批准规则

只有以下条件全部满足才能把 frame 写为 `review_status: "approved"`：

- reviewer 实际打开并检查了该帧；
- reviewer 与 annotator 不是同一个人；
- 分歧已经有书面结论；
- 该帧对象列表是最终版本；
- frame number 和 timestamp 与 5 FPS 抽帧一致。

## 9. Original PII gold manifest

从仓库模板开始：

```bash
cp media_service/evaluation/gold_manifest.template.json \
  private-gold-workspace/manifests/original_pii_gold_manifest.json
```

每个视频块必须包含：source SHA-256、URL/内部编号、creator、license、sampling profile、
sample FPS、split 和 frames。示例：

```json
{
  "frame_number": 123,
  "timestamp_ms": 24400,
  "review_status": "approved",
  "annotator": "victoria",
  "reviewer": "reviewer-b",
  "difficult_case_tags": ["motion_blur", "small_object"],
  "objects": [
    {
      "id": "A01-face-01-f123",
      "label": "face",
      "annotation_type": "bbox",
      "track_id": "A01-face-01",
      "geometry": {"x": 0.214, "y": 0.103, "width": 0.084, "height": 0.146}
    }
  ]
}
```

空负例使用 `"objects": []`，不能直接删掉该 frame。尚未审核的帧必须保持 `pending`，评估器会忽略它。

完成并交叉审核 task 后，用辅助工具自动导出，避免手抄几百帧坐标。`--tags` 是可选的困难场景
sidecar，例如 `{"12":["low_light"],"13":["motion_blur","small_object"]}`：

```bash
cd media_service
.venv/bin/python scripts/export_pii_gold_manifest.py TASK_ID \
  --output /private/path/manifests/original_pii_gold_manifest.json \
  --annotator victoria --reviewer reviewer-b --split test \
  --source-url "internal://A01" \
  --source-creator "team-capture" \
  --source-license "consented-internal-evaluation" \
  --tags /private/path/qa/A01-tags.json
```

工具会计算源文件 SHA-256，把 mask 的 `geometry.bbox` 转成 detector gold bbox，带入可用的模型
track ID，并明确写出所有空负例帧。第二个视频使用相同命令并增加 `--append`。如果输出已存在但没有
`--append`，工具会停止而不是覆盖已有 gold。导出后审核者仍须抽查 JSON；自动转换不能代替人工复核。

## 10. 生成首检预测并评分

每个视频运行一次，参数必须与 manifest 相同：

```bash
cd media_service
.venv/bin/python scripts/evaluate_pipeline.py /private/path/A01.mp4 \
  --model-kind pii \
  --sample-fps 5 \
  --include-predictions \
  --source-url "internal://A01" \
  --source-creator "team-capture" \
  --source-license "consented-internal-evaluation" \
  --output /private/path/reports/original-pii-A01.json
```

冻结的 test split 评分：

```bash
.venv/bin/python scripts/evaluate_gold.py \
  /private/path/manifests/original_pii_gold_manifest.json \
  /private/path/reports/original-pii-*.json \
  --mode pii --split test --iou-threshold 0.5 \
  --output /private/path/metrics/original_pii_gold_metrics.json
```

当前质量门槛：face recall ≥ 0.98，license plate 和 screen recall ≥ 0.95。只在 test 中该类别确实
存在 gold objects 时才评估该门槛。不要为了通过门槛删除困难帧或正例。

## 11. 生成正常脱敏视频

回到已完成的 annotation task：

1. 使用 `Mask +` 补足应该模糊的像素；
2. 使用 `Mask −` 删除明显多余区域；
3. 输入独立 reviewer ID；
4. 点击 `Export privacy-safe video`；
5. 等待 residual scan；
6. 只有 `COMPLETED` 且 `PASSED` 才下载 sanitized video、manifest 和 bundle；
7. 核对 manifest 中的 source/output SHA-256、reviewer、模型 revision 和处理时间。

如果状态为 `FAILED`，不要手工把失败视频当成安全视频。根据 finding 回到 mask 修正，重新导出并保留
失败 manifest 作为审计证据。

## 12. Residual PII Gold：脱敏后泄漏标注

### 12.1 为什么必须有 positive controls

如果所有正常 sanitized 视频都没有任何可辨认 PII，那么数据集可以测误报，却无法证明二检模型能找到
泄漏。零正例数据得到的 recall 没有意义，项目评估器会明确返回 `not measurable`。

因此 residual gold 必须同时包含：

- clean negatives：正常严格脱敏的视频；
- positive controls：故意漏掉或缩小少量 mask 后得到的私有测试视频；
- difficult positives：低光、运动模糊、小目标、遮挡、屏幕反光等泄漏。

positive controls 只用于内部 detector 评估，必须放在私有目录，文件名包含
`DO_NOT_RELEASE_RESIDUAL_CONTROL`，不得上传 GitHub、发送客户或混入正常 sanitized bundle。

### 12.2 如何安全制作 positive controls

只使用团队自摄、演员同意、虚构车牌、合成屏幕内容：

1. 在隔离的本地数据库/worker 中复制 task 或创建私有评估 task，移除一个 mask；
2. 每段只制造少量已知泄漏，记录对象和时间；
3. 运行 FFmpeg 脱敏生成控制视频；
4. 人工确认该对象在输出中仍然可辨认；
5. 给 frame 添加 `positive_control` 和相应困难 tag；
6. 完成评估后按保留策略删除视频，仅保留 hash 和聚合指标。

不要用真实陌生人的脸或真实车牌制造泄漏控制。
正常生产 worker 会 fail-closed 并删除检测到泄漏的输出，这是正确行为。若需要生成 positive control，
只能在与正式数据隔离的本地环境临时以 `MEDIA_RESIDUAL_PII_SCAN=false` 启动专用 worker；输出 manifest
必须显示 `SKIPPED`，文件必须命名为 `DO_NOT_RELEASE_RESIDUAL_CONTROL-*`。完成后立即关闭该 worker，
恢复默认 `true`。不得在共享/生产 worker 上关闭 residual scan。

### 12.3 Residual gold 标注标准

标注对象必须是在**输出视频中仍可辨认**的区域：

- 模糊充分、无法辨认的脸不标 residual face；
- 仍能读出或识别结构的车牌标 residual license plate；
- 屏幕敏感内容仍可辨认时标 residual screen；
- 未被 mask 覆盖的任何 PII 标 residual；
- clean negative 帧保留 `objects: []`。

Residual gold 仍使用 tight bbox，不使用原始 mask。标注者不得先看 Grounding DINO 结果；完成并冻结
gold 后才能生成预测，否则容易产生 confirmation bias。

实际操作时，把每个 sanitized clean/control 文件作为一个新视频重新上传，仍选择 `Action · 5 FPS`。
创建一个新的 annotation task，不点击 `PII` 推理按钮，先独立人工标出输出中仍可辨认的 residual PII；
clean negative 的所有帧保存为空。完成交叉审核后点击 `Complete task`。该派生视频必须与对应原视频使用
相同 split。

### 12.4 Residual manifest 和预测

从专用模板开始：

```bash
cp media_service/evaluation/residual_gold_manifest.template.json \
  private-gold-workspace/manifests/residual_pii_gold_manifest.json
```

注意 `source.sha256` 必须是 sanitized/control 输出文件的 hash，不是原始视频 hash。

也可以直接用同一个自动导出工具创建 residual manifest；此时 `TASK_ID` 必须属于重新上传的
sanitized/control 视频：

```bash
cd media_service
.venv/bin/python scripts/export_pii_gold_manifest.py RESIDUAL_TASK_ID \
  --output /private/path/manifests/residual_pii_gold_manifest.json \
  --dataset-name sanitized-video-residual-pii-gold-v1 \
  --annotator reviewer-b --reviewer victoria --split test \
  --source-url "private://sanitized-A01" \
  --source-creator "privacy-pipeline" \
  --source-license "consented-internal-evaluation"
```

其他 residual 视频继续使用 `--append`。导出后核对 JSON 中的 source hash 确实等于 sanitized/control
文件，而不是原始上传。

对每个 sanitized/control 视频运行独立二检：

```bash
cd media_service
.venv/bin/python scripts/evaluate_residual_pipeline.py \
  /private/path/sanitized-A01.mp4 \
  --sample-fps 5 --confidence 0.25 \
  --output /private/path/reports/residual-pii-A01.json
```

评分：

```bash
.venv/bin/python scripts/evaluate_gold.py \
  /private/path/manifests/residual_pii_gold_manifest.json \
  /private/path/reports/residual-pii-*.json \
  --mode residual-pii --split test \
  --max-residual-miss-rate 0 \
  --output /private/path/metrics/residual_pii_gold_metrics.json
```

生产前门槛是 observed residual miss rate = 0。必须同时报告测试正例数量和 95% 置信解释，不能只写
“100% recall”。如果存在漏检，保存失败案例、修正 prompt/模型/阈值，只能在 validation 上调参，
最后对冻结 test 重新运行一次。

## 13. 最终 QA 清单

### 素材和权限

- [ ] 每个原视频、sanitized 视频和 positive control 都有 SHA-256
- [ ] 每个来源都有授权/同意证据
- [ ] Git 中没有原始 PII、抽帧图片或泄漏控制视频
- [ ] 同一视频及其派生物没有跨 split

### 标注

- [ ] face / license_plate / screen 定义一致
- [ ] 每个 approved frame 有 annotator 和不同的 reviewer
- [ ] 空负例明确保留 `objects: []`
- [ ] PII detector gold 使用 tight bbox，不是 padded mask
- [ ] track IDs 在连续帧中稳定
- [ ] 所有分歧已记录并裁决
- [ ] 困难 tags 有实际依据

### Original PII 评估

- [ ] prediction report 带 `--include-predictions`
- [ ] report source hash 与 gold manifest 完全相同
- [ ] sample FPS 都是 5
- [ ] test 中三个类别都有足够正例
- [ ] 保存 overall、by_label、by_difficult_case、track coverage 和 FN/min

### Residual PII 评估

- [ ] gold 基于 rendered sanitized/control 文件
- [ ] 包含 clean negatives 和经过同意的 positive controls
- [ ] positive controls 由两个人批准且明确禁止发布
- [ ] 使用独立 Grounding DINO report
- [ ] manifest/report 的 sanitized source hash 一致
- [ ] residual miss rate 为 0 或明确记录未通过
- [ ] 没有用“零正例数据集”宣称 100% recall

### 最终签字

```markdown
Dataset version:
Repository commit:
Original manifest SHA-256:
Residual manifest SHA-256:
Original metrics SHA-256:
Residual metrics SHA-256:
Annotator A:
Annotator B:
Final reviewer A:
Final reviewer B:
Unresolved cases: 0 / 非 0（说明）
Date:
```

## 14. 常见错误

| 错误 | 后果 | 正确做法 |
| --- | --- | --- |
| 只标模型检测出来的对象 | 无法发现模型 FN，recall 虚高 | 每帧人工完整扫描并补漏 |
| 把 PII mask 直接作为 detector gold | IoU 定义不一致 | 使用 mask 中的 tight `geometry.bbox` |
| 不保留空帧 | 无法测 false positives | 批准 `objects: []` 帧 |
| 同一人标注并审核 | 缺乏独立复核 | 两人交叉审核 |
| 相邻帧随机分 train/test | temporal leakage | 按原始视频划分 |
| 调参时查看 test 错误 | test 不再独立 | 只在 validation 调整 |
| residual 数据全是干净视频 | 漏检率不可测 | 加入私有 positive controls |
| positive control 含真实陌生人 PII | 隐私风险 | 使用同意演员、虚构牌照、合成屏幕 |
| 文件重编码后沿用旧 hash | 报告和 gold 无法匹配 | 每个派生文件重新 hash |
| 把 FAILED sanitized export 发出去 | 可能存在泄漏 | 只有 COMPLETED/PASSED 可交付 |

## 15. 完工标准

团队成员交回工作时，不是简单说“标完了”，而是交付：

1. 自己负责视频的 source inventory 和权限证据；
2. 完整 Original PII 标注及 Victoria 的交叉审核结果；
3. 自己对 Victoria 视频的审核记录；
4. 自己负责的 sanitized clean 和 private positive controls；
5. Original 和 residual prediction reports；
6. 合并后两个 manifest 的复核结果；
7. `disagreements.md` 和零 unresolved case 证明；
8. 两份 metrics JSON；
9. `final-signoff.md`；
10. 明确列出仍然失败的类别、困难切片和下一步，而不是隐藏失败。

做到这些，项目才能诚实地说明：数据来源可追溯，标注经过双人审核，首检准确率可复现，脱敏输出经过
独立模型检查，residual 漏检率来自真实 gold labels，而不是模型自我验证。

## 16. 仓库内参考资料

- `README.md`：项目总览
- `docs/annotation-workflow.md`：标注界面和快捷键
- `docs/model-assisted-labeling.md`：Accept/Correct/Reject 流程
- `docs/review-and-dataset-health.md`：复核队列和一致性指标
- `docs/privacy-sanitization.md`：像素 mask、FFmpeg 和审计导出
- `docs/pii-gold-evaluation.md`：PII / residual 评分命令
- `docs/residual-pii-smoke.md`：独立二检真实运行证据
- `media_service/evaluation/gold_manifest.schema.json`：manifest schema
- `media_service/evaluation/gold_manifest.template.json`：Original gold 模板
- `media_service/evaluation/residual_gold_manifest.template.json`：Residual gold 模板
- `media_service/scripts/evaluate_pipeline.py`：首检报告生成器
- `media_service/scripts/export_pii_gold_manifest.py`：从已复核 task 自动生成/追加 Original gold
- `media_service/scripts/evaluate_residual_pipeline.py`：独立二检报告生成器
- `media_service/scripts/evaluate_gold.py`：最终评分器
