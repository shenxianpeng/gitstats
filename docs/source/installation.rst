
**Requirements**

- Git (obviously)
- Python 3.9+
- Pip or Pipx

**From source**
You can install from source by cloning the repository and running:
.. code-block:: bash

    pip install .

**From PyPI**
You can install from PyPI by running:
.. code-block:: bash

    pip install gitstats

Or if you want to install with ``pipx``:
.. code-block:: bash

    pipx install gitstats

**Docker**
There is a Docker image available at https://ghcr.io/shenxianpeng/gitstats.
To use it, you can run:
.. code-block:: bash

    docker run -it --rm -v /path/to/your/repo:/repo -v /path/to/output:/output ghcr.io/shenxianpeng/gitstats:latest /repo /output
