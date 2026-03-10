欢迎使用 GitStats 文档！
=========================

.. figure:: https://raw.githubusercontent.com/shenxianpeng/gitstats/main/docs/source/logo.png
   :alt: 项目 Logo
   :align: center
   :width: 200px

``gitstats`` 是一个从 Git 仓库生成可视化统计报告的 Python 工具。

它可以生成包含提交、作者、活跃度、文件、代码行数、标签等统计信息的 HTML/JSON 报告。

安装
----

.. code-block:: bash

   pip install gitstats

用法
----

.. code-block:: bash

   gitstats <git路径> <输出路径>

运行 ``gitstats --help`` 查看更多选项，或阅读 :doc:`getting-started` 了解详情。

功能特性
--------

* **概览**：总文件数、代码行数、提交数、作者数、项目年龄。
* **活跃度**：按小时、星期、月份、年份统计的提交活动。
* **作者**：作者列表（姓名、提交数、首次/最后提交日期）、月度/年度最佳作者。
* **文件**：按日期统计的文件数量、文件扩展名统计。
* **代码行**：按日期统计的代码行数。
* **标签**：按日期和作者统计的标签。
* **可定制**：通过 ``gitstats.conf`` 自定义配置。
* **跨平台**：支持 Linux、Windows 和 macOS。

在线示例：https://shenxianpeng.github.io/gitstats/index.html

.. toctree::
   :maxdepth: 2
   :caption: 快速入门

   getting-started
   configuration
   integration
   ai-integration
   faq

.. toctree::
   :maxdepth: 2
   :caption: 关于

   license
   contributors
   changelog
