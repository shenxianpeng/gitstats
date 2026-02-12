AI Integration
==============

GitStats supports AI-powered analysis to provide intelligent insights and natural language summaries of your repository statistics. This feature uses various AI services to generate detailed analysis of your project's development patterns, team collaboration, and code evolution.

Overview
--------

AI-powered features enhance GitStats reports by providing detailed, natural language summaries and actionable recommendations on:

* **Project Overview**: Comprehensive analysis of development history and project health
* **Activity Patterns**: Insights into commit frequency, development rhythm, and temporal patterns
* **Code Evolution**: Understanding of codebase growth, code churn, and maintenance patterns

Additional capabilities:

* **Analyzing patterns**: Identifying trends in commit activity, team collaboration, and code growth
* **Providing insights**: Offering actionable recommendations based on repository statistics
* **Generating summaries**: Creating natural language explanations of complex metrics
* **Supporting multiple languages**: Available in English, Chinese, Japanese, Korean, Spanish, French, German, and more

Installation
------------

To use AI features, install GitStats with AI dependencies:

.. code-block:: bash

   pip install gitstats[ai]

This installs the required packages for all supported AI providers.

Supported AI Providers
----------------------

GitStats supports multiple AI providers, each offering different models and capabilities. Refer to each provider's documentation for available models and pricing.

OpenAI
~~~~~~

The most popular AI service with GPT-4 and GPT-3.5-turbo models.

**Setup:**

1. Get your API key from `OpenAI <https://platform.openai.com/api-keys>`_

2. Set environment variable or configuration:

.. code-block:: bash

   export OPENAI_API_KEY=sk-...

3. Configure in ``gitstats.conf``:

.. code-block:: ini

   [gitstats]
   ai_enabled = true
   ai_provider = openai
   ai_model = gpt-4

**Usage:**

.. code-block:: bash

   gitstats --ai --ai-provider openai --ai-model gpt-4 /path/to/repo output/

Anthropic Claude
~~~~~~~~~~~~~~~~

High-quality AI models known for detailed analysis.

**Setup:**

1. Get your API key from `Anthropic <https://console.anthropic.com/>`_

2. Set environment variable:

.. code-block:: bash

   export ANTHROPIC_API_KEY=sk-ant-...

3. Configure in ``gitstats.conf``:

.. code-block:: ini

   [gitstats]
   ai_enabled = true
   ai_provider = claude
   ai_model = claude-3-5-sonnet-20241022

**Usage:**

.. code-block:: bash

   gitstats --ai --ai-provider claude /path/to/repo output/

Google Gemini
~~~~~~~~~~~~~

Google's advanced AI model for analysis and insights.

**Setup:**

1. Get your API key from `Google AI Studio <https://aistudio.google.com/app/api-keys>`_

2. Set environment variable:

.. code-block:: bash

   export GOOGLE_API_KEY=...

3. Configure in ``gitstats.conf``:

.. code-block:: ini

   [gitstats]
   ai_enabled = true
   ai_provider = gemini
   ai_model = gemini-pro

**Usage:**

.. code-block:: bash

   gitstats --ai --ai-provider gemini /path/to/repo output/

Ollama (Local LLM)
~~~~~~~~~~~~~~~~~~

Run AI models locally without sending data to external services.

**Setup:**

1. Install Ollama from `ollama.ai <https://ollama.ai/>`_

2. Pull a model:

.. code-block:: bash

   ollama pull llama2
   # or
   ollama pull mistral
   ollama pull codellama

3. Configure in ``gitstats.conf``:

.. code-block:: ini

   [gitstats]
   ai_enabled = true
   ai_provider = ollama
   ai_model = llama2
   ollama_base_url = http://localhost:11434

**Usage:**

.. code-block:: bash

   gitstats --ai --ai-provider ollama --ai-model llama2 /path/to/repo output/

**Benefits:**

* Complete privacy - data never leaves your machine
* No API costs
* Works offline

Configuration
-------------

Command Line Options
~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Enable AI features
   gitstats --ai /path/to/repo output/

   # Disable AI (override config)
   gitstats --no-ai /path/to/repo output/

   # Select AI provider
   gitstats --ai --ai-provider openai /path/to/repo output/

   # Specify model
   gitstats --ai --ai-model gpt-4-turbo /path/to/repo output/

   # Language for summaries
   gitstats --ai --ai-language zh /path/to/repo output/

   # Force refresh AI cache
   gitstats --ai --refresh-ai /path/to/repo output/

Configuration File
~~~~~~~~~~~~~~~~~~

Edit ``gitstats.conf`` to set default AI options:

.. code-block:: ini

   [gitstats]
   # Enable AI features
   ai_enabled = true

   # AI provider: openai, claude, gemini, ollama
   ai_provider = openai

   # API key (or use environment variable)
   ai_api_key =

   # Model to use
   ai_model = gpt-4

   # Language for summaries (en, zh, ja, ko, es, fr, de)
   ai_language = en

   # Cache AI summaries to save costs
   ai_cache_enabled = true

   # Retry settings
   ai_max_retries = 3
   ai_retry_delay = 1

   # Ollama base URL (for local LLM)
   ollama_base_url = http://localhost:11434

Language Support
----------------

AI summaries can be generated in multiple languages:

* **en**: English
* **zh**: Chinese
* **ja**: Japanese
* **ko**: Korean
* **es**: Spanish
* **fr**: French
* **de**: German

Example:

.. code-block:: bash

   # Chinese summaries
   gitstats --ai --ai-language zh /path/to/repo output/

   # Japanese summaries
   gitstats --ai --ai-language ja /path/to/repo output/

Caching
-------

AI-generated summaries are cached by default to save API costs and time. The cache is stored in the output directory under ``.ai_cache/``.

**Cache Behavior:**

* Summaries are reused if the data hasn't changed
* Different AI providers/models have separate caches
* Language changes invalidate the cache

**Force Refresh:**

.. code-block:: bash

   gitstats --ai --refresh-ai /path/to/repo output/

**Disable Caching:**

In ``gitstats.conf``:

.. code-block:: ini

   [gitstats]
   ai_cache_enabled = false

Error Handling
--------------

GitStats handles AI errors gracefully:

* **Network issues**: Retries with exponential backoff
* **API errors**: Shows error message in report, continues generation
* **Missing API keys**: Provides clear error message
* **Rate limits**: Retries after delay

If AI generation fails, the report is still generated with all standard statistics - AI insights are simply omitted.

Best Practices
--------------

1. **API Costs**: Enable caching to avoid regenerating summaries
2. **Privacy**: Use Ollama for sensitive repositories
3. **Model Selection**:

   * GPT-4: Best quality, higher cost
   * GPT-3.5-turbo: Good balance
   * Llama2: Free, local, good for testing

4. **Language**: Match the language to your team's preference
5. **Refreshing**: Only use ``--refresh-ai`` when you need updated analysis

Troubleshooting
---------------

**"AI provider not initialized" error**

* Check that you've installed AI dependencies: ``pip install gitstats[ai]``
* Verify your API key is set correctly

**"Failed after N attempts" error**

* Check your internet connection
* Verify API key is valid and has credits
* Check service status (OpenAI, Anthropic, etc.)

**Summaries not appearing in report**

* Ensure ``--ai`` flag is used or ``ai_enabled = true`` in config
* Check console output for error messages
* Verify AI dependencies are installed

**Ollama connection errors**

* Ensure Ollama is running: ``ollama serve``
* Check the base URL is correct (default: ``http://localhost:11434``)
* Verify the model is pulled: ``ollama list``

**Slow generation**

* First run is slower (generates and caches summaries)
* Subsequent runs use cache and are much faster
* Local models (Ollama) may be slower but have no API costs

Examples
--------

**Full-featured Analysis with OpenAI:**

.. code-block:: bash

   export OPENAI_API_KEY=sk-...
   gitstats --ai --ai-provider openai --ai-model gpt-4 --ai-language en /path/to/repo output/

**Privacy-focused Local Analysis:**

.. code-block:: bash

   ollama pull llama2
   gitstats --ai --ai-provider ollama --ai-model llama2 /path/to/repo output/

**Chinese Analysis with Claude:**

.. code-block:: bash

   export ANTHROPIC_API_KEY=sk-ant-...
   gitstats --ai --ai-provider claude --ai-model claude-3-5-sonnet-20241022 --ai-language zh /path/to/repo output/

**Configuration-based Approach:**

Create ``gitstats.conf``:

.. code-block:: ini

   [gitstats]
   ai_enabled = true
   ai_provider = openai
   ai_model = gpt-4
   ai_language = en
   ai_cache_enabled = true

Then simply run:

.. code-block:: bash

   export OPENAI_API_KEY=sk-...
   gitstats /path/to/repo output/
