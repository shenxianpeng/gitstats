# 配置

你可以在当前目录下创建 `gitstats.conf` 文件来自定义配置。

| 键 | 描述 | 默认值 |
|----|------|--------|
| `max_domains` | "按提交统计的域名"中显示的最大域名数 | `10` |
| `max_ext_length` | 统计中显示的文件扩展名最大长度 | `10` |
| `style` | 生成报告的 CSS 样式表 | `gitstats.css` |
| `max_authors` | "作者"列表中显示的最大作者数 | `20` |
| `authors_top` | 突出显示的顶级作者数 | `5` |
| `commit_begin` | 提交范围的起始位置（空 = 包含所有提交），例如 `10` 表示最后 10 个提交 | `""` |
| `commit_end` | 提交范围的终点 | `HEAD` |
| `linear_linestats` | 启用代码行统计的线性历史（`1` = 启用，`0` = 禁用） | `1` |
| `project_name` | 显示的项目名称（默认：仓库目录名） | `""` |
| `processes` | 收集数据时使用的并行进程数 | `8` |
| `start_date` | 提交的起始日期，作为 `--since` 参数传递给 Git。格式：`YYYY-MM-DD` | `""` |
| `end_date` | 提交的结束日期，作为 `--until` 参数传递给 Git。格式：`YYYY-MM-DD` | `""` |
| `authors` | 以逗号分隔的作者列表（OR 逻辑）。如果为空，则包含所有作者 | `""` |
| `exclude_exts` | 以逗号分隔的文件扩展名列表，用于从代码行计数中排除。包含空字节的文件会被自动检测为二进制文件并额外排除 | `""` |

## 配置文件示例

```ini
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
```

## 命令行覆盖

你也可以使用 `-c key=value` 选项覆盖配置值：

```bash
gitstats . report -c max_authors=10 -c authors_top=3
```

## 筛选示例

```bash
# 按日期范围筛选提交
gitstats . report -c start_date=2024-01-01 -c end_date=2024-12-31

# 按指定作者筛选提交
gitstats . report -c authors="John Doe,Jane Smith"

# 组合多个筛选条件
gitstats . report -c start_date=2024-01-01 -c authors="John Doe"
```
