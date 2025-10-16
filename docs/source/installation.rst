Installation
============

.. important::

    The following requirements need to be installed before using ``gitstats``

    - Python 3.10+ (https://www.python.org/downloads/)
    - Git (http://git-scm.com/)
    - Gnuplot (http://www.gnuplot.info): You can install Gnuplot on

        - Ubuntu with ``sudo apt install gnuplot``
        - macOS with ``brew install gnuplot``
        - Windows with ``choco install gnuplot``

You can install gitstats with pip:

.. code-block:: bash

    pip install gitstats

Or you can also get gitstats Docker image.

.. tip::

    The Docker image has all the dependencies (Python, Git, Gnuplot and gitstats) already installed.

.. code-block:: bash

    docker run ghcr.io/shenxianpeng/gitstats:latest
