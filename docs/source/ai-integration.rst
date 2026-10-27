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
* **Supporting multiple languages**: English, Chinese, Japanese, Korean, Spanish, French and German, and any other language the model writes (see `Language Support`_)

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

2. Set the environment variable:

.. code-block:: bash

   export OPENAI_API_KEY=sk-...

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

**Usage:**

.. code-block:: bash

   gitstats --ai --ai-provider claude /path/to/repo output/

The default model is ``claude-opus-5-5``; ``--ai-model`` picks another one,
such as ``claude-sonnet-5-5``. It needs ``anthropic`` 1.0 or later, which
``pip install gitstats[ai]`` installs.

Google Gemini
~~~~~~~~~~~~~

Google's advanced AI model for analysis and insights.

**Setup:**

1. Get your API key from `Google AI Studio <https://aistudio.google.com/app/api-keys>`_

2. Set environment variable:

.. code-block:: bash

   export GOOGLE_API_KEY=...

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

**Usage:**

.. code-block:: bash

   gitstats --ai --ai-provider ollama --ai-model llama2 /path/to/repo output/

   # Ollama on another address
   gitstats --ai --ai-provider ollama -c ollama_base_url=http://gpu-box:11434 /path/to/repo output/

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

Not in gitstats.conf
~~~~~~~~~~~~~~~~~~~~

The AI settings (``ai_*``, ``ollama_*``) are taken from the command line and
the environment only. A ``gitstats.conf`` in the current directory is ignored
for them, with a warning: it often comes with the repository being analyzed,
and whoever commits to that repository could otherwise turn AI on and send its
data to a server of their choosing (see :doc:`configuration`). Use the options
above, ``-c key=value`` for the others, and an environment variable for the
API key:

.. code-block:: bash

   export OPENAI_API_KEY=sk-...
   gitstats --ai --ai-provider openai --ai-model gpt-4 \
     -c ai_cache_enabled=true -c ai_max_retries=3 -c ai_retry_delay=1 \
     /path/to/repo output/

What Is Sent to the AI Provider
-------------------------------

The prompt holds the statistics of the report and, with them, text taken from
the repository's history: the **names of the authors** (the top contributors,
and the newcomers of each year) and a sample of **commit subjects** for each
year. All of it goes to the provider you choose; with Ollama it stays on the
machine that runs Ollama. Do not use a hosted provider for a repository whose
author names or commit messages must not leave your organization.

Anyone who can commit to the repository writes some of that text, and so can
steer what the model answers. The answer is treated as untrusted: the report
keeps only its paragraphs, lists and emphasis (``<p>``, ``<ul>``, ``<ol>``,
``<li>``, ``<strong>``, ``<em>``, ``<code>``), without attributes, drops any
``<script>`` or ``<style>`` with its content, and escapes the rest. Error
messages are always escaped, and the History page shows its narration as
plain text.

Language Support
----------------

``--ai-language`` takes a language code. For these, the summaries and the AI
Insights page's own headings are in that language:

* **en**: English
* **zh**: Chinese
* **ja**: Japanese
* **ko**: Korean
* **es**: Spanish
* **fr**: French
* **de**: German

Any other code (``pt``, ``it``, ``vi``...) is passed to the model, which
writes the summaries in that language when it can; the page's headings stay
in English.

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

.. code-block:: bash

   gitstats --ai -c ai_cache_enabled=false /path/to/repo output/

Error Handling
--------------

The report is always written, with all the standard statistics:

* **Busy or failing service** (HTTP 429 or 5xx) and **connection errors**: the
  call is made again after 1, 2, 4... seconds, ``ai_max_retries`` calls in all
  (3 unless set, ``-c ai_max_retries=1`` for one call only).
* **No answer** within ``ai_timeout`` seconds (120 unless set): that page's
  summary fails, and the next pages are not asked for, since they would most
  likely wait as long.
* **A request the service refuses** (a wrong key or model, a model not pulled
  in Ollama): not retried; the reason the service gives is shown.
* Each summary that fails is on the AI Insights page as "Analysis
  Unavailable", with the reason, and the console says how many of the
  summaries were written.
* **No AI package or no API key**: one warning, and the report without the AI
  Insights page.
* **Ctrl-C** while the summaries are being written stops them; the report is
  then written without them.

.. code-block:: bash

   # wait up to five minutes for a slow local model
   gitstats --ai --ai-provider ollama -c ai_timeout=300 /path/to/repo output/

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

**"No AI summaries: ... package not installed" or "... API key not found"**

* Check that you've installed AI dependencies: ``pip install gitstats[ai]``
* Verify your API key is set correctly

**"Failed after N attempts" error**

* Check your internet connection
* Verify API key is valid and has credits
* Check service status (OpenAI, Anthropic, etc.)

**Summaries not appearing in report**

* Ensure the ``--ai`` flag is used (``ai_enabled`` in ``gitstats.conf`` is ignored)
* Check console output for error messages
* Verify AI dependencies are installed

**Ollama connection errors**

* Ensure Ollama is running: ``ollama serve``
* Check the base URL is correct (default: ``http://localhost:11434``)
* Verify the model is pulled: ``ollama list`` (the page then says
  "Ollama: model '...' not found, try pulling it first")

**Slow generation**

* First run is slower (generates and caches summaries)
* Subsequent runs use cache and are much faster
* Local models (Ollama) may be slower but have no API costs; raise
  ``-c ai_timeout=...`` if a model needs more than two minutes per answer

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
   gitstats --ai --ai-provider claude --ai-language zh /path/to/repo output/

**Same Settings for Every Run:**

The AI settings cannot come from ``gitstats.conf``; a shell alias keeps them in
one place:

.. code-block:: bash

   alias gitstats-ai='gitstats --ai --ai-provider openai --ai-model gpt-4 --ai-language en'
   export OPENAI_API_KEY=sk-...
   gitstats-ai /path/to/repo output/
