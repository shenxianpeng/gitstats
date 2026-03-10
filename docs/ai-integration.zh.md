# AI 集成

GitStats 支持 AI 驱动的分析，提供智能洞察和自然语言摘要。此功能使用各种 AI 服务来生成项目开发模式、团队协作和代码演进的详细分析。

## 概述

AI 驱动的功能通过提供详细的自然语言摘要和可操作的建议来增强 GitStats 报告：

- **项目概览**：开发历史和项目健康状况的综合分析
- **活动模式**：提交频率、开发节奏和时间模式的洞察
- **代码演进**：理解代码库增长、代码变动和维护模式

其他功能：

- **分析模式**：识别提交活动、团队协作和代码增长的趋势
- **提供洞察**：基于仓库统计数据提供可操作的建议
- **生成摘要**：创建复杂指标的自然语言解释
- **多语言支持**：支持英文、中文、日文、韩文、西班牙文、法文、德文等

## 安装

要使用 AI 功能，请安装带有 AI 依赖的 GitStats：

```bash
pip install gitstats[ai]
```

这会安装所有支持的 AI 提供商所需的包。

## 支持的 AI 提供商

GitStats 支持多个 AI 提供商，每个提供商提供不同的模型和功能。请参阅各提供商的文档了解可用模型和定价。

### OpenAI

最流行的 AI 服务，提供 GPT-4 和 GPT-3.5-turbo 模型。

**设置：**

1. 从 [OpenAI](https://platform.openai.com/api-keys) 获取 API 密钥

2. 设置环境变量：

    ```bash
    export OPENAI_API_KEY=sk-...
    ```

3. 在 `gitstats.conf` 中配置：

    ```ini
    [gitstats]
    ai_enabled = true
    ai_provider = openai
    ai_model = gpt-4
    ```

**使用：**

```bash
gitstats --ai --ai-provider openai --ai-model gpt-4 /path/to/repo output/
```

### Anthropic Claude

以详细分析著称的高质量 AI 模型。

**设置：**

1. 从 [Anthropic](https://console.anthropic.com/) 获取 API 密钥

2. 设置环境变量：

    ```bash
    export ANTHROPIC_API_KEY=sk-ant-...
    ```

3. 在 `gitstats.conf` 中配置：

    ```ini
    [gitstats]
    ai_enabled = true
    ai_provider = claude
    ai_model = claude-3-5-sonnet-20241022
    ```

**使用：**

```bash
gitstats --ai --ai-provider claude /path/to/repo output/
```

### Google Gemini

Google 的先进 AI 模型，用于分析和洞察。

**设置：**

1. 从 [Google AI Studio](https://aistudio.google.com/app/api-keys) 获取 API 密钥

2. 设置环境变量：

    ```bash
    export GOOGLE_API_KEY=...
    ```

3. 在 `gitstats.conf` 中配置：

    ```ini
    [gitstats]
    ai_enabled = true
    ai_provider = gemini
    ai_model = gemini-pro
    ```

**使用：**

```bash
gitstats --ai --ai-provider gemini /path/to/repo output/
```

### Ollama（本地大模型）

在本地运行 AI 模型，无需将数据发送到外部服务。

**设置：**

1. 从 [ollama.ai](https://ollama.ai/) 安装 Ollama

2. 拉取模型：

    ```bash
    ollama pull llama2
    # 或
    ollama pull mistral
    ollama pull codellama
    ```

3. 在 `gitstats.conf` 中配置：

    ```ini
    [gitstats]
    ai_enabled = true
    ai_provider = ollama
    ai_model = llama2
    ollama_base_url = http://localhost:11434
    ```

**使用：**

```bash
gitstats --ai --ai-provider ollama --ai-model llama2 /path/to/repo output/
```

**优势：**

- 完全隐私——数据不会离开你的机器
- 无 API 费用
- 离线可用

## 配置

### 命令行选项

```bash
# 启用 AI 功能
gitstats --ai /path/to/repo output/

# 禁用 AI（覆盖配置）
gitstats --no-ai /path/to/repo output/

# 选择 AI 提供商
gitstats --ai --ai-provider openai /path/to/repo output/

# 指定模型
gitstats --ai --ai-model gpt-4-turbo /path/to/repo output/

# 摘要语言
gitstats --ai --ai-language zh /path/to/repo output/

# 强制刷新 AI 缓存
gitstats --ai --refresh-ai /path/to/repo output/
```

### 配置文件

编辑 `gitstats.conf` 设置默认 AI 选项：

```ini
[gitstats]
# 启用 AI 功能
ai_enabled = true

# AI 提供商：openai, claude, gemini, ollama
ai_provider = openai

# API 密钥（或使用环境变量）
ai_api_key =

# 使用的模型
ai_model = gpt-4

# 摘要语言（en, zh, ja, ko, es, fr, de）
ai_language = en

# 缓存 AI 摘要以节省费用
ai_cache_enabled = true

# 重试设置
ai_max_retries = 3
ai_retry_delay = 1

# Ollama 地址（用于本地大模型）
ollama_base_url = http://localhost:11434
```

## 语言支持

AI 摘要可以使用多种语言生成：

| 代码 | 语言 |
|------|------|
| `en` | 英文 |
| `zh` | 中文 |
| `ja` | 日文 |
| `ko` | 韩文 |
| `es` | 西班牙文 |
| `fr` | 法文 |
| `de` | 德文 |

```bash
# 中文摘要
gitstats --ai --ai-language zh /path/to/repo output/

# 日文摘要
gitstats --ai --ai-language ja /path/to/repo output/
```

## 缓存

AI 生成的摘要默认会被缓存以节省 API 费用和时间。缓存存储在输出目录的 `.ai_cache/` 下。

**缓存行为：**

- 如果数据未更改，摘要将被复用
- 不同的 AI 提供商/模型有独立的缓存
- 更改语言会使缓存失效

**强制刷新：**

```bash
gitstats --ai --refresh-ai /path/to/repo output/
```

**禁用缓存**，在 `gitstats.conf` 中：

```ini
[gitstats]
ai_cache_enabled = false
```

## 错误处理

GitStats 优雅地处理 AI 错误：

- **网络问题**：使用指数退避重试
- **API 错误**：在报告中显示错误信息，继续生成
- **缺少 API 密钥**：提供清晰的错误信息
- **速率限制**：延迟后重试

如果 AI 生成失败，报告仍会包含所有标准统计数据——只是省略 AI 洞察。

## 最佳实践

1. **API 费用**：启用缓存以避免重复生成摘要
2. **隐私**：对敏感仓库使用 Ollama
3. **模型选择**：
    - GPT-4：最佳质量，费用较高
    - GPT-3.5-turbo：性价比好
    - Llama2：免费，本地运行，适合测试
4. **语言**：根据团队偏好选择语言
5. **刷新**：仅在需要更新分析时使用 `--refresh-ai`

## 故障排除

**"AI provider not initialized" 错误**

- 检查是否已安装 AI 依赖：`pip install gitstats[ai]`
- 验证 API 密钥是否正确设置

**"Failed after N attempts" 错误**

- 检查网络连接
- 验证 API 密钥是否有效且有余额
- 检查服务状态（OpenAI、Anthropic 等）

**摘要未出现在报告中**

- 确保使用了 `--ai` 标志或在配置中设置了 `ai_enabled = true`
- 检查控制台输出的错误信息
- 验证 AI 依赖是否已安装

**Ollama 连接错误**

- 确保 Ollama 正在运行：`ollama serve`
- 检查地址是否正确（默认：`http://localhost:11434`）
- 验证模型是否已拉取：`ollama list`

**生成速度慢**

- 首次运行较慢（生成并缓存摘要）
- 后续运行使用缓存，速度会快很多
- 本地模型（Ollama）可能较慢，但没有 API 费用

## 示例

**使用 OpenAI 的全功能分析：**

```bash
export OPENAI_API_KEY=sk-...
gitstats --ai --ai-provider openai --ai-model gpt-4 --ai-language en /path/to/repo output/
```

**注重隐私的本地分析：**

```bash
ollama pull llama2
gitstats --ai --ai-provider ollama --ai-model llama2 /path/to/repo output/
```

**使用 Claude 的中文分析：**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
gitstats --ai --ai-provider claude --ai-model claude-3-5-sonnet-20241022 --ai-language zh /path/to/repo output/
```

**基于配置文件的方式：**

创建 `gitstats.conf`：

```ini
[gitstats]
ai_enabled = true
ai_provider = openai
ai_model = gpt-4
ai_language = en
ai_cache_enabled = true
```

然后运行：

```bash
export OPENAI_API_KEY=sk-...
gitstats /path/to/repo output/
```
