# C9 MVP 说明 · DEK 0.1.0

**学生**：Zhouruoying（2025105400318）　**周次**：W1

> 本文对应挑战申请文件清单中的「MVP」。MVP 本体是仓库里的 `dek/` 包与 `tests/`，本文只说明如何拿到它、如何验证它真的能跑。

---

## 1. 拿到（零依赖，无需安装）

```bash
git clone https://github.com/zhou96754128/cs146s-c9-dek-zh
cd cs146s-c9-dek-zh
python3 --version          # 需要 ≥3.9
python3 -m dek --help
```

无第三方依赖，不需要 `pip install`、不需要虚拟环境（`pyproject.toml` 仅供后续发布到 PyPI 用）。

---

## 2. 四条命令（MVP 全部能力）

| 命令 | 作用 |
|---|---|
| `python3 -m dek init <dir>` | 扫描目录生成清单骨架 `dek.json` |
| `python3 -m dek verify --root <dir> --manifest <file>` | 逐条核验声明，输出 `VERDICT=PASS/FAIL` |
| `python3 -m dek inventory --root <dir> --out <file>` | 生成文件指纹清单（path / bytes / sha256） |
| `python3 -m dek render <report.json> --out <report.html>` | 把核验结果渲染成离线 HTML |

退出码：`0` 通过 / `1` 核验失败 / `2` 清单或参数不合法。

---

## 3. 三分钟自证（本人实测输出）

**① 45 个单元测试**
```bash
python3 -m unittest discover -s tests
# Ran 45 tests in 0.108s
# OK
```

**② 正向 demo 必须 PASS**
```bash
python3 -m dek verify --root examples/demo --manifest dek.json
# VERDICT=PASS  total=12  pass=12  fail=0  skip=0
```

**③ 回归夹具必须 FAIL（关键）**
```bash
python3 -m dek verify --root examples/regression_c6a --manifest dek.json
# VERDICT=FAIL  total=2  pass=1  fail=1
```
这一条返回 `0` 才是灾难——说明工具在无差别放行。夹具里 `screenshot.png` 是真实的 523426 字节，清单里故意写着 C6A 当时错记的 `226315`，`diff=297111`。

**④ 拿自己核验自己**
```bash
python3 -m dek verify --root . --manifest dek.json
# VERDICT=PASS  total=24  pass=24  fail=0  skip=0
```

---

## 4. MVP 边界（不做什么）

- 不签名、不追供应链（只做「指纹不符即失败」这一截）
- 不做代码风格检查（只回答声明与实物是否一致）
- `repro` 命令在本机执行，不做容器隔离
- `render` 样式朴素，无增量核验、无并行

---

## 5. 证据落盘位置

| 文件 | 内容 |
|---|---|
| `evidence/demo_verify.log` | demo 正向核验原始输出 |
| `evidence/regression_verify.log` | 回归负向核验原始输出 |
| `evidence/inventory.json` | 仓库文件指纹清单（33 项，含本清单自身） |
| `evidence/demo_report.json` / `.html` | 核验报告 JSON 与离线渲染页 |
| `ci/github-actions-ci.yml` | ubuntu + macOS × Python 3.9/3.12 四组合，含「回归必须返回 1」硬断言；发布通道 token 无 `workflow` 权限，故配置以 `ci/` 路径随仓库提供，启用命令见 README（尚未在 GitHub 上真实跑过） |
