常见问题
========

1. 如何生成非 master 分支的统计数据？

    使用 ``-c commit_end=devel`` 参数。

2. 我的 Git 仓库中有些文件想要从统计中排除，该怎么做？

    目前唯一的方法是使用 `git-filter-branch(1) <https://git-scm.com/docs/git-filter-branch>`_ 创建一个临时仓库，然后从该仓库生成统计数据。

3. 当同一作者使用不同的姓名或邮箱提交时，如何合并作者信息？

    使用 Git 的 ``.mailmap`` 功能，详见 `gitmailmap <https://git-scm.com/docs/gitmailmap>`_ 文档。
