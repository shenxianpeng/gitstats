配置
====

你可以在当前目录中创建 ``gitstats.conf`` 文件来自定义配置。

* ``max_domains`` - "按提交统计的域名" 中显示的最大域名数。默认值：``10``。
* ``max_ext_length`` - 统计信息中显示的文件扩展名最大长度。默认值：``10``。
* ``style`` - 生成报告使用的 CSS 样式表。默认值：``gitstats.css``。
* ``max_authors`` - "作者" 列表中显示的最大作者数。默认值：``20``。
* ``authors_top`` - 高亮显示的顶级作者数量。默认值：``5``。
* ``commit_begin`` - 提交范围的起始位置（为空则包含所有提交）。例如 ``10`` 表示最近 10 次提交。默认值：``""``（空）。
* ``commit_end`` - 提交范围的结束位置。默认值：``HEAD``。
* ``linear_linestats`` - 为行统计启用线性历史（``1`` = 启用，``0`` = 禁用）。默认值：``1``。
* ``project_name`` - 显示的项目名称（默认为仓库目录名）。默认值：``""``（空）。
* ``processes`` - 收集数据时使用的并行进程数。默认值：``8``。
* ``start_date`` - 提交的起始日期，作为 --since 参数传递给 Git（可选）。格式：``YYYY-MM-DD``。默认值：``""``（空）。
* ``end_date`` - 提交的截止日期，作为 --until 参数传递给 Git（可选）。格式：``YYYY-MM-DD``。默认值：``""``（空）。
* ``authors`` - 用逗号分隔的作者列表，用于过滤提交。只包含这些作者的提交（使用 OR 逻辑：列出的任何作者的提交都会被包含）。如果为空，则包含所有作者。默认值：``""``（空）。
* ``exclude_exts`` - 用逗号分隔的文件扩展名列表，用于从行计数中排除。如果为空，则不排除任何文件。内容中包含空字节的文件会自动被检测为二进制文件并从行计数中排除。此检测在 exclude_exts 指定的扩展名之外额外进行。默认值：``""``（空）。

以下是一个 ``gitstats.conf`` 示例文件：

.. code-block:: ini

   [gitstats]
   max_domains = 10
   max_ext_length = 10
   style = gitstats.css
   max_authors = 20
   authors_top = 5
   commit_begin = 10
   commit_end = HEAD
   linear_linestats = 1
   project_name =
   processes = 8
   start_date =
   end_date =
   authors =
   exclude_exts = png,jpg,bin,exe,dll,class,jar,zip,tar

你也可以在运行 ``gitstats`` 命令时使用 ``-c key=value`` 选项来覆盖配置值。

例如：

.. code-block:: bash

   gitstats . report -c max_authors=10 -c authors_top=3

此命令将生成最多显示 10 位作者、高亮显示前 3 位作者的报告。

过滤示例：

.. code-block:: bash

   # 按日期范围过滤提交
   gitstats . report -c start_date=2024-01-01 -c end_date=2024-12-31

   # 按特定作者过滤提交
   gitstats . report -c authors="John Doe,Jane Smith"

   # 组合多个过滤条件
   gitstats . report -c start_date=2024-01-01 -c authors="John Doe"
