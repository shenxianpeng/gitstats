<div align="center">
  <img src="https://raw.githubusercontent.com/shenxianpeng/gitstats/main/docs/source/logo.png" alt="项目 Logo" width="200px">
</div>

[![PyPI - Version](https://img.shields.io/pypi/v/gitstats?color=blue)](https://pypi.org/project/gitstats/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/gitstats)](https://pypi.org/project/gitstats/)
[![PyPI Downloads](https://static.pepy.tech/badge/gitstats/week)](https://pepy.tech/projects/gitstats)
[![Test](https://github.com/shenxianpeng/gitstats/actions/workflows/test.yml/badge.svg)](https://github.com/shenxianpeng/gitstats/actions/workflows/test.yml)
[![Docs](https://img.shields.io/badge/docs-mkdocs--material-blue)](https://shenxianpeng.github.io/gitstats/docs/)
[![GitHub contributors](https://img.shields.io/github/contributors/shenxianpeng/gitstats)](https://github.com/shenxianpeng/gitstats/graphs/contributors)

# `$ gitstats`

📊 从 Git 仓库生成可视化统计报告。

## 示例

`gitstats . report` 生成如下 [gitstats 报告](https://shenxianpeng.github.io/gitstats/report/index.html)。

## 安装

```bash
pip install gitstats
```

gitstats 兼容 Python 3.9 及更高版本。

## 使用方法

```bash
gitstats <git仓库路径> <输出路径>
```

运行 `gitstats --help` 查看更多选项，或查阅[入门指南](getting-started.md)。

## v2.0.0 新特性

v2.0.0 是一个重大版本更新，专注于现代化报告界面并移除 Gnuplot 依赖。

**终端风格的界面重新设计**

整个报告界面以终端 / OpenCode 风格重新设计：
零圆角（棱角分明的直角）、标题和导航栏使用等宽字体、
边框为主的布局、GitHub 风格的绿色热力图。支持明暗两种模式，
一键切换——切换页面时无样式闪烁。

**Chart.js 替代 Gnuplot**

所有图表现在使用 [Chart.js](https://www.chartjs.org/) 在浏览器中交互式渲染。
不再需要 Gnuplot。报告是完全自包含的 HTML 文件。

## 功能特性

以下是 `gitstats` 的部分功能：

- **概览**：总文件数、代码行数、提交数、作者数、项目年龄。
- **活动**：按小时、星期几、周内小时、月份、年月、年份统计的提交活动。
- **作者**：作者列表（姓名、提交数（%）、首次提交日期、最后提交日期、活跃时长）、月度最佳作者、年度最佳作者。
- **文件**：按日期统计的文件数量、文件扩展名统计。
- **代码行数**：按日期统计的代码行数变化。
- **标签**：按日期和作者统计的标签。
- **可配置**：通过 `gitstats.conf` 自定义配置。
- **跨平台**：支持 Linux、Windows 和 macOS。

## AI 驱动的功能 🤖

GitStats 支持 AI 驱动的洞察分析，通过自然语言摘要和可操作的建议增强你的仓库分析。

**快速开始：**

```bash
# 安装 AI 支持
pip install gitstats[ai]

# 使用 OpenAI 启用 AI
export OPENAI_API_KEY=your-api-key
gitstats --ai --ai-provider openai <git仓库路径> <输出路径>
```

详细的安装说明、配置选项和示例，请参阅 [AI 集成](ai-integration.md)页面。

## 贡献

作为一个开源项目，gitstats 欢迎各种形式的贡献。

---

gitstats 项目最初由 [Heikki Hokkanen](https://github.com/hoxu) 创建，目前由 [Xianpeng Shen](https://github.com/shenxianpeng) 维护。
