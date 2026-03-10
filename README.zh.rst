.. start-of-about

.. figure:: https://raw.githubusercontent.com/shenxianpeng/gitstats/main/docs/source/logo.png
   :alt: 项目 Logo
   :align: center
   :width: 200px

.. |pypi-version| image:: https://img.shields.io/pypi/v/gitstats?color=blue
   :target: https://pypi.org/project/gitstats/
   :alt: PyPI - Version

.. |python-versions| image:: https://img.shields.io/pypi/pyversions/gitstats
   :alt: PyPI - Python Version

.. |python-download| image:: https://static.pepy.tech/badge/gitstats/week
   :target: https://pepy.tech/projects/gitstats
   :alt: PyPI Downloads

.. |test-badge| image:: https://github.com/shenxianpeng/gitstats/actions/workflows/test.yml/badge.svg
   :target: https://github.com/shenxianpeng/gitstats/actions/workflows/test.yml
   :alt: Test

.. |sonarcloud| image:: https://sonarcloud.io/api/project_badges/measure?project=shenxianpeng_gitstats&metric=alert_status
   :target: https://sonarcloud.io/summary/new_code?id=shenxianpeng_gitstats
   :alt: Quality Gate Status

.. |docs-badge| image:: https://readthedocs.org/projects/gitstats/badge/?version=latest
   :target: https://gitstats.readthedocs.io/
   :alt: Documentation

.. |contributors| image:: https://img.shields.io/github/contributors/shenxianpeng/gitstats
   :target: https://github.com/shenxianpeng/gitstats/graphs/contributors
   :alt: GitHub contributors

|pypi-version| |python-versions| |python-download| |test-badge| |docs-badge| |contributors|

`English <README.rst>`_ | `中文 <zh/README.zh.rst>`_

``$ gitstats``
===============

📊 从 Git 仓库生成可视化统计报告。

📘 文档：`gitstats.readthedocs.io <https://gitstats.readthedocs.io/>`_

示例
----

``gitstats . report`` 生成如下 `gitstats 报告 <https://shenxianpeng.github.io/gitstats/index.html>`_。

安装
----

.. code-block:: bash

   pip install gitstats


gitstats 兼容 Python 3.9 及更高版本。


使用方法
--------

.. code-block:: bash

   gitstats <git仓库路径> <输出路径>


运行 ``gitstats --help`` 查看更多选项，或查阅 `文档 <https://gitstats.readthedocs.io/en/latest/getting-started.html>`_。

v2.0.0 新特性
--------------

v2.0.0 是一个重大版本更新，专注于现代化报告界面并移除 Gnuplot 依赖。

**终端风格的界面重新设计**
   整个报告界面以终端 / OpenCode 风格重新设计：
   零圆角（棱角分明的直角）、标题和导航栏使用等宽字体、
   边框为主的布局、GitHub 风格的绿色热力图。支持明暗两种模式，
   一键切换——切换页面时无样式闪烁。

**Chart.js 替代 Gnuplot**
   所有图表现在使用 `Chart.js <https://www.chartjs.org/>`_ 在浏览器中交互式渲染。
   不再需要 Gnuplot。报告是完全自包含的 HTML 文件。

功能特性
--------

以下是 ``gitstats`` 的部分功能：

* **概览**：总文件数、代码行数、提交数、作者数、项目年龄。
* **活动**：按小时、星期几、周内小时、月份、年月、年份统计的提交活动。
* **作者**：作者列表（姓名、提交数（%）、首次提交日期、最后提交日期、活跃时长）、月度最佳作者、年度最佳作者。
* **文件**：按日期统计的文件数量、文件扩展名统计。
* **代码行数**：按日期统计的代码行数变化。
* **标签**：按日期和作者统计的标签。
* **可配置**：通过 ``gitstats.conf`` 自定义配置。
* **跨平台**：支持 Linux、Windows 和 macOS。

AI 驱动的功能 🤖
------------------

GitStats 支持 AI 驱动的洞察分析，通过自然语言摘要和可操作的建议增强你的仓库分析。

**快速开始：**

.. code-block:: bash

   # 安装 AI 支持
   pip install gitstats[ai]

   # 使用 OpenAI 启用 AI
   export OPENAI_API_KEY=your-api-key
   gitstats --ai --ai-provider openai <git仓库路径> <输出路径>

详细的安装说明、配置选项和示例，请参阅 `AI 集成文档 <https://gitstats.readthedocs.io/en/stable/ai-integration.html>`_。

.. end-of-about

贡献
----

作为一个开源项目，gitstats 欢迎各种形式的贡献。

----

gitstats 项目最初由 `Heikki Hokkainen <https://github.com/hoxu>`_ 创建，目前由 `Xianpeng Shen <https://github.com/shenxianpeng>`_ 维护。
