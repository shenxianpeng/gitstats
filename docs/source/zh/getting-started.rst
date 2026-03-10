入门指南
========

前提条件
--------

在使用 gitstats 之前，请确保已安装以下软件：

- **Python 3.9+** - 从 https://www.python.org/downloads/ 下载
- **Git** - 从 https://git-scm.com/ 下载

.. note::

    从 ``2.0.0`` 版本开始，gitstats 使用 `Chart.js <https://www.chartjs.org/>`_\ （随报告捆绑）来渲染图表，以实现更现代的可视化效果和更好的性能。

安装
----

使用 `pip <https://pip.pypa.io/en/stable/>`_ 安装 `gitstats <https://pypi.org/project/gitstats/>`_：

.. code-block:: bash

    pip install gitstats

快速开始
--------

运行以下命令生成基本报告：

.. code-block:: bash

    gitstats . report

.. tip::

    你也可以使用 `uv <https://docs.astral.sh/uv/>`_ 一条命令下载并运行 gitstats：

    .. code-block:: bash

        uvx gitstats . report

其中：

- ``.`` 是当前目录（你的 Git 仓库），你可以指定任意 Git 仓库路径。
- ``report`` 是生成 HTML 文件的输出目录。

查看在线示例：https://shenxianpeng.github.io/gitstats/index.html


生成 JSON 格式的报告
---------------------

同时生成 HTML 和 JSON 格式：

.. code-block:: bash

    gitstats . report --format json

这会在 HTML 报告旁生成一个 ``report.json`` 文件。

.. tip::
   使用 `jq <https://jqlang.github.io/jq/>`_ 解析 JSON 文件：

   .. code-block:: bash

       cat report.json | jq .

   这样你可以提取特定数据或与其他工具集成。


命令行用法
----------

基本语法
~~~~~~~~

.. code-block:: bash

    gitstats [选项] <git仓库路径> <输出路径>

**参数：**

- ``<git仓库路径>`` - Git 仓库的路径（例如 ``.`` 表示当前目录）
- ``<输出路径>`` - 生成报告的目录

**选项：**

- ``-h, --help`` - 显示帮助信息并退出
- ``-v, --version`` - 显示程序版本号
- ``-c key=value, --config key=value`` - 覆盖配置值（可多次使用）
- ``-f {json}, --format {json}`` - 生成额外的输出格式

完整帮助输出
~~~~~~~~~~~~

.. code-block:: text

    usage: gitstats [-h] [-v] [-c key=value] [-f {json}] <gitpath> <outputpath>

    Generate statistics for a Git repository.

    positional arguments:
      <gitpath>             Path(s) to the Git repository.
      <outputpath>          Path to the directory where the output will be stored.

    options:
      -h, --help            show this help message and exit
      -v, --version         show program's version number and exit
      -c key=value, --config key=value
                            Override configuration value. Can be specified multiple
                            times. See configuration documentation for available options.
      -f {json}, --format {json}
                            Generate additional output format.

示例
----

为当前目录生成报告：

.. code-block:: bash

    gitstats . my-report

为指定仓库生成报告：

.. code-block:: bash

    gitstats /path/to/repo output-folder

生成带 JSON 输出的报告：

.. code-block:: bash

    gitstats . report --format json

覆盖配置值：

.. code-block:: bash

    gitstats . report -c max_authors=10 -c authors_top=3

更多配置选项，请参阅 :doc:`configuration` 页面。
