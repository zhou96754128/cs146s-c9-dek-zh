# DEK — Delivery Evidence Kit

**一句话定义**：把一堆 AI 生成的散落产物，变成一个「每个数字都能追到来源文件、每份必交物都按文件名通配核对、每条复现命令都真的跑过」的可复核交付包。

零依赖（只用 Python 3.9+ 标准库），单文件 HTML 报告，可直接进 CI。

## 为什么需要它

我做课程挑战时，被打回和被扣分不是因为做得少，而是因为**说的和盘上的不一致**。真实发生过的四件事：

| 事故 | 真实后果 | DEK 里对应的断言 |
|---|---|---|
| 文档写「截图 226315 字节」，盘上实际 523426 字节 | AI 评语直接指认数字不可信 | `claim` + `kind=file_size` |
| 必交物写成目录条目 `screenshots/` | 平台按文件逐条比对，永远匹配不上，`ready=false` | `deliverable`：只匹配**文件**，目录永不命中 |
| 必交物 URL 只写在 README 正文里 | 平台按**文件名通配**判定，连查 24 次 `NOT_FOUND`，提交没落库 | `deliverable` + `pattern="*app链接*"` |
| 「入口脚本已通过」靠自述，没真跑 | 评语指认「入口脚本未被实际运行」 | `repro`：真跑、比退出码、比输出标记 |

核心理念只有一句：**别信任何人的自述，包括 AI 的，也包括我自己的。**

## 安装

```bash
git clone <repo>
cd Zhouruoying_C9_dek
python3 -m unittest discover -s tests -v   # 45 项自检
```

不需要 `pip install`。直接在仓库根运行 `python3 -m dek`。

## 三条命令

```bash
# 1) 采集证据指纹
python3 -m dek inventory --root . --out evidence/inventory.json

# 2) 按清单核验（0 全通过 / 1 有失败 / 2 清单不合法）
python3 -m dek verify --root . --manifest dek.json \
        --json evidence/report.json --html evidence/report.html

# 3) 生成起步清单
python3 -m dek init --root .
```

## 清单格式（`dek.json`）

四段，前两段必填：

```json
{
  "project": "my-delivery",
  "claims": [
    {"id": "文件字节", "kind": "file_size", "source": "out/report.pdf", "value": 103093},
    {"id": "解题数",   "kind": "json", "source": "out/summary.json", "pointer": "run.n_solved", "value": 11},
    {"id": "指纹",     "kind": "sha256_prefix", "source": "out/report.pdf", "value": "89bcde5c", "length": 16}
  ],
  "deliverables": [
    {"pattern": "*proposal*", "required": true},
    {"pattern": "*AAR_W*",    "required": true},
    {"pattern": "*demo*",     "required": false}
  ],
  "repro": [
    {"id": "单测", "cmd": "python3 -m unittest discover -s tests", "expect_exit": 0, "expect_stdout": "OK"}
  ]
}
```

### `claims` 支持的 `kind`

| kind | 从哪取实际值 | 说明 |
|---|---|---|
| `json`（默认） | `source` 里的 JSON，按 `pointer` 点路径取值 | 也可指向字段数组下标 `items.0.name` |
| `file_size` | 文件的字节数 | |
| `sha256` / `sha256_prefix` | 文件 sha256（可截取前 `length` 位） | |
| `line_count` | 按行切分后的行数 | |
| `contains` / `not_contains` | 文本是否包含 `value` | 用于占位符扫描、「必须写明」类检查 |
| `file_exists` | 文件是否存在 | |

数值类断言支持 `tolerance`；`string` 断言要求**完全相等**（不做模糊匹配，这是刻意的）。

### 退出码语义

- `0`：所有断言 PASS
- `1`：至少一条 FAIL
- `2`：清单/参数本身不合法（不算核验失败，避免「配置错了当通过」）

## 与同类工具的关系（拿来主义）

| 工具 | 它解决什么 | DEK 借了什么 | DEK 不做什么 |
|---|---|---|---|
| `make` / `pre-commit` | 命令级门禁 | 退出码即结论 | 不做代码风格检查 |
| `dbt tests` | 数据表断言 | 断言声明与执行分离 | 不连数据库 |
| SLSA provenance | 产物来源可追溯 | 指纹 + 来源文件绑定 | 不做签名链 |
| 评测脚手架（Eval Harness） | 跑模型打分 | 报告即证据 | 不评估内容质量 |

DEK 的定位很窄：**只回答「你文档里说的，和盘上的是不是同一个东西」**。它不判断内容好坏，也不生成内容。

## 局限（诚实声明）

- `repro` 用 shell 执行，不做沙箱隔离；只在你自己的仓库里跑。
- 不校验远端仓库与本地是否一致（那是 `git fetch` 的职责）。
- 同一路径既是文件又是目录的极端情况未处理。
- 报告页没有交互钻取，纯静态快照。

## 许可

MIT，见 `LICENSE`。
