# FAQ

**1. How do I generate statistics for a branch other than master?**

Use the `-c commit_end=devel` option.

**2. I have some files in my Git repository that I want to exclude from the statistics. How?**

The only way currently is to create a temporary repository using
[git-filter-branch(1)](https://git-scm.com/docs/git-filter-branch) and generate statistics from that.

**3. How do I merge author information when the same author commits with different names or emails?**

Use Git's `.mailmap` feature, see the [gitmailmap](https://git-scm.com/docs/gitmailmap) documentation.
