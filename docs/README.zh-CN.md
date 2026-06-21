# Open Equity Research 中文说明

Open Equity Research 是一套“证据优先”的美股投研工作流。输入股票代码后，它会从 SEC EDGAR 获取原始披露，保存快照，整理年度财务指标，建立主张—证据账本，运行基本面、反方和风险筛查，并生成可审计的 Markdown 研究报告。

它不是自动交易系统：没有券商接口、不下单、不输出个性化买卖建议。估值模块也不会直接运行，必须先由人修改并确认假设。

## 核心价值

普通 AI 投资回答容易把事实、推断和故事混在一起。本项目强制区分：

- **原始证据**：SEC 文件中的 XBRL 数字和 10-K 原文；
- **派生指标**：自由现金流、净现金、利润率等可复算公式；
- **观察结论**：由规则产生、必须引用 evidence ID；
- **研究假设**：可能成立，但仍需行业、竞争、管理层和市场数据；
- **投资决定**：始终在自动工作流之外，由人负责。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp oer.example.toml oer.toml
```

编辑 `oer.toml`：

```toml
[open_equity_research]
workspace = "research"
sec_user_agent = "你的名字 your@email.com"
request_interval_seconds = 0.15
```

SEC 要求自动访问声明身份和联系方式。本项目默认限速约每秒 6.7 次请求，低于 SEC 公布的每秒 10 次上限。

## 使用

```bash
# 生成研究包
equity-research research AAPL

# 查看状态
equity-research status AAPL

# 检查证据引用和文件完整性
equity-research verify AAPL
```

主要报告位于：

```text
research/AAPL/report.md
```

## 估值门禁

第一次研究后会生成 `valuation_assumptions.json`，其中：

```json
"human_reviewed": false
```

你需要用公司特定、可解释的假设替换模板，并将其改为 `true`，系统才允许运行 DCF：

```bash
equity-research value AAPL --price 210.00
```

这个 DCF 只是简单情景模型。银行、保险、REIT、早期公司和强周期企业通常需要专门模型。

## 接入大模型

系统会生成四个隔离任务：

- Fundamental：解释经营和财务轨迹；
- Bear：主动寻找反例和最强看空逻辑；
- Risk：检查数据、模型、估值和现实风险；
- Verifier：核对每个主张是否真的被证据支持。

可通过本地命令适配任意模型：

```bash
equity-research agents AAPL \
   --command "python examples/mock_agent.py"
```

模型输出会被标记为不可信，不能自动升级成事实证据。

## 当前边界

0.1 版重点是 SEC 基本面证据链，暂时不含实时行情、财报电话会、新闻、行业数据库、组合管理和回测。10-K 章节提取是启发式的，XBRL 标签也可能因公司而异，必须回到原始文件核查。

本项目只用于研究和教育，不构成投资建议。投资可能导致本金部分或全部损失。
