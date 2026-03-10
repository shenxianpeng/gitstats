AI 集成
=======

GitStats 支持 AI 驱动的分析功能，为你的仓库统计数据提供智能洞察和自然语言摘要。此功能使用各种 AI 服务来生成项目开发模式、团队协作和代码演变的详细分析。

概述
----

AI 驱动的功能通过以下方面的详细自然语言摘要和可操作建议来增强 GitStats 报告：

* **项目概览**：开发历史和项目健康状况的全面分析
* **活跃度模式**：提交频率、开发节奏和时间模式的洞察
* **代码演变**：代码库增长、代码变更和维护模式的理解

其他功能：

* **分析模式**：识别提交活动、团队协作和代码增长的趋势
* **提供洞察**：基于仓库统计数据提供可操作的建议
* **生成摘要**：为复杂指标创建自然语言解释
* **多语言支持**：支持英语、中文、日语、韩语、西班牙语、法语、德语等

安装
----

要使用 AI 功能，请安装带有 AI 依赖的 GitStats：

.. code-block:: bash

   pip install gitstats[ai]

这将安装所有支持的 AI 提供商所需的软件包。

支持的 AI 提供商
-----------------

GitStats 支持多个 AI 提供商，每个提供商提供不同的模型和功能。请参阅各提供商的文档了解可用模型和定价。

OpenAI
~~~~~~

最流行的 AI 服务，提供 GPT-4 和 GPT-3.5-turbo 模型。

**设置：**

1. 从 `OpenAI <https://platform.openai.com/api-keys>`_ 获取 API 密钥

2. 设置环境变量或配置：

.. code-block:: bash

   export OPENAI_API_KEY=sk-...

3. 在 ``gitstats.conf`` 中配置：

.. code-block:: ini

   [gitstats]
   ai_enabled = true
   ai_provider = openai
   ai_model = gpt-4

**用法：**

.. code-block:: bash

   gitstats --ai --ai-provider openai --ai-model gpt-4 /path/to/repo output/

Anthropic Claude
~~~~~~~~~~~~~~~~

以高质量分析著称的 AI 模型。

**设置：**

1. 从 `Anthropic <https://console.anthropic.com/>`_ 获取 API 密钥

2. 设置环境变量：

.. code-block:: bash

   export ANTHROPIC_API_KEY=sk-ant-...

3. 在 ``gitstats.conf`` 中配置：

.. code-block:: ini

   [gitstats]
   ai_enabled = true
   ai_provider = claude
   ai_model = claude-3-5-sonnet-20241022

**用法：**

.. code-block:: bash

   gitstats --ai --ai-provider claude /path/to/repo output/

Google Gemini
~~~~~~~~~~~~~

Google 的高级 AI 模型，用于分析和洞察。

**设置：**

1. 从 `Google AI Studio <https://aistudio.google.com/app/api-keys>`_ 获取 API 密钥

2. 设置环境变量：

.. code-block:: bash

   export GOOGLE_API_KEY=...

3. 在 ``gitstats.conf`` 中配置：

.. code-block:: ini

   [gitstats]
   ai_enabled = true
   ai_provider = gemini
   ai_model = gemini-pro

**用法：**

.. code-block:: bash

   gitstats --ai --ai-provider gemini /path/to/repo output/

Ollama（本地大语言模型）
~~~~~~~~~~~~~~~~~~~~~~~~

在本地运行 AI 模型，无需将数据发送到外部服务。

**设置：**

1. 从 `ollama.ai <https://ollama.ai/>`_ 安装 Ollama

2. 拉取模型：

.. code-block:: bash

   ollama pull llama2
   # 或者
   ollama pull mistral
   ollama pull codellama

3. 在 ``gitstats.conf`` 中配置：

.. code-block:: ini

   [gitstats]
   ai_enabled = true
   ai_provider = ollama
   ai_model = llama2
   ollama_base_url = http://localhost:11434

**用法：**

.. code-block:: bash

   gitstats --ai --ai-provider ollama --ai-model llama2 /path/to/repo output/

**优势：**

* 完全隐私——数据不会离开你的机器
* 无 API 费用
* 离线可用

配置
----

命令行选项
~~~~~~~~~~

.. code-block:: bash

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

配置文件
~~~~~~~~

编辑 ``gitstats.conf`` 设置默认 AI 选项：

.. code-block:: ini

   [gitstats]
   # 启用 AI 功能
   ai_enabled = true

   # AI 提供商：openai、claude、gemini、ollama
   ai_provider = openai

   # API 密钥（或使用环境变量）
   ai_api_key =

   # 使用的模型
   ai_model = gpt-4

   # 摘要语言（en、zh、ja、ko、es、fr、de）
   ai_language = en

   # 缓存 AI 摘要以节省费用
   ai_cache_enabled = true

   # 重试设置
   ai_max_retries = 3
   ai_retry_delay = 1

   # Ollama 基础 URL（用于本地大语言模型）
   ollama_base_url = http://localhost:11434

语言支持
--------

AI 摘要可以生成多种语言版本：

* **en**：英语
* **zh**：中文
* **ja**：日语
* **ko**：韩语
* **es**：西班牙语
* **fr**：法语
* **de**：德语

示例：

.. code-block:: bash

   # 中文摘要
   gitstats --ai --ai-language zh /path/to/repo output/

   # 日语摘要
   gitstats --ai --ai-language ja /path/to/repo output/

缓存
----

默认情况下，AI 生成的摘要会被缓存以节省 API 费用和时间。缓存存储在输出目录的 ``.ai_cache/`` 下。

**缓存行为：**

* 如果数据未更改，摘要将被重复使用
* 不同的 AI 提供商/模型有各自的缓存
* 更改语言会使缓存失效

**强制刷新：**

.. code-block:: bash

   gitstats --ai --refresh-ai /path/to/repo output/

**禁用缓存：**

在 ``gitstats.conf`` 中：

.. code-block:: ini

   [gitstats]
   ai_cache_enabled = false

错误处理
--------

GitStats 能够优雅地处理 AI 错误：

* **网络问题**：使用指数退避进行重试
* **API 错误**：在报告中显示错误信息，继续生成
* **缺少 API 密钥**：提供清晰的错误提示
* **速率限制**：延迟后重试

如果 AI 生成失败，报告仍会生成所有标准统计数据——AI 洞察只是被省略了。

最佳实践
--------

1. **API 费用**：启用缓存以避免重新生成摘要
2. **隐私保护**：对敏感仓库使用 Ollama
3. **模型选择**：

   * GPT-4：最佳质量，费用较高
   * GPT-3.5-turbo：质量和费用的良好平衡
   * Llama2：免费、本地、适合测试

4. **语言**：根据团队偏好匹配语言
5. **刷新**：仅在需要更新分析时使用 ``--refresh-ai``

故障排除
--------

**"AI provider not initialized" 错误**

* 检查是否已安装 AI 依赖：``pip install gitstats[ai]``
* 验证 API 密钥是否正确设置

**"Failed after N attempts" 错误**

* 检查网络连接
* 验证 API 密钥是否有效且有余额
* 检查服务状态（OpenAI、Anthropic 等）

**摘要未出现在报告中**

* 确保使用了 ``--ai`` 标志或在配置中设置了 ``ai_enabled = true``
* 检查控制台输出的错误信息
* 验证是否已安装 AI 依赖

**Ollama 连接错误**

* 确保 Ollama 正在运行：``ollama serve``
* 检查基础 URL 是否正确（默认：``http://localhost:11434``）
* 验证模型是否已拉取：``ollama list``

**生成速度慢**

* 首次运行较慢（生成并缓存摘要）
* 后续运行使用缓存，速度更快
* 本地模型（Ollama）可能较慢但无 API 费用

示例
----

**使用 OpenAI 进行全功能分析：**

.. code-block:: bash

   export OPENAI_API_KEY=sk-...
   gitstats --ai --ai-provider openai --ai-model gpt-4 --ai-language en /path/to/repo output/

**注重隐私的本地分析：**

.. code-block:: bash

   ollama pull llama2
   gitstats --ai --ai-provider ollama --ai-model llama2 /path/to/repo output/

**使用 Claude 进行中文分析：**

.. code-block:: bash

   export ANTHROPIC_API_KEY=sk-ant-...
   gitstats --ai --ai-provider claude --ai-model claude-3-5-sonnet-20241022 --ai-language zh /path/to/repo output/

**基于配置文件的方式：**

创建 ``gitstats.conf``：

.. code-block:: ini

   [gitstats]
   ai_enabled = true
   ai_provider = openai
   ai_model = gpt-4
   ai_language = en
   ai_cache_enabled = true

然后简单运行：

.. code-block:: bash

   export OPENAI_API_KEY=sk-...
   gitstats /path/to/repo output/
