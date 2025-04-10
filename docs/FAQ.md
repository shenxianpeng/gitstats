# FAQ

1. How do I generate statistics of a non-master branch?

    Use the `-c commit_end=devel` parameter.

2. I have files in my git repository that I would like to exclude from the statistics. How do I do that?

    At the moment, the only way is to use [git-filter-branch(1)](https://git-scm.com/docs/git-filter-branch) to create a temporary repository and generate the statistics from that.

3. How do I merge author information when the same author has made commits using different names or emails?

    Use Git's `.mailmap` feature, as described in the [gitmailmap](https://git-scm.com/docs/gitmailmap) documentation.
