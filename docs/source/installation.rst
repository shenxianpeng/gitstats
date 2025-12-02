Installation
============

.. important::

    The following requirements need to be installed before using ``gitstats``

    - Python 3.9+ (https://www.python.org/downloads/)
    - Git (http://git-scm.com/)

You can install gitstats with pip:

.. code-block:: bash

    pip install gitstats

.. note::

    Starting from version 0.9.0, gitstats uses `gnuplot-wheel <https://pypi.org/project/gnuplot-wheel/>`_ package which bundles gnuplot as a Python dependency. You no longer need to install gnuplot separately!

Or you can also get gitstats Docker image.

.. tip::

    The Docker image has all the dependencies (Python, Git, and gitstats) already installed.

.. code-block:: bash

    docker run ghcr.io/shenxianpeng/gitstats:latest
