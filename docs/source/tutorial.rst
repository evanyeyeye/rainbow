.. _tutorial:

Tutorial
========

Start by importing the library.

.. code-block:: python

   import rainbow as rb 

The main way to use **rainbow** is to feed it a directory path. 

.. code-block:: python 

   datadir = rb.read("red.D")
   print(datadir)

Now :code:`datadir` is a DataDirectory object. Normal printing will display the name of each parsed binary file from the directory.

A DataFile object is created for each of these binary files. A list of every DataFile can be accessed with the :code:`datafiles` attribute. 

.. code-block:: python 

   for datafile in datadir.datafiles:
       print(datafile.name, datafile.detector)

Each DataFile can also be retrived by name using the :code:`get_file` method. 

.. code-block:: python

   datafile = datadir.get_file("DAD1B.ch")

The :code:`get_info` method returns a string with detailed information about the data. It is available at both the DataDirectory and DataFile levels.

.. code-block:: python

   print(datadir.get_info())

The output would look something like:

.. code-block::

   =====
   red.D 
   =====
   Directory Metadata: {'vendor': 'Agilent', 'date': '27-Feb-18, 10:11:50', 'vialpos': '23'}

   --------
   DAD1B.ch
   --------
   Detector: UV
   Xlabels: [5.20000000e-03 1.18666667e-02 1.85333333e-02 ... 1.39852000e+01
    1.39918667e+01 1.39985333e+01]
   Ylabels: ['280.0']
   Data: [[-0.02656132]
    [-0.03028661]
    [-0.03784895]
    ...
    [-0.93856454]
    [-0.93948841]
    [-0.94015151]]
   Metadata: {'notebook': 'usp', 'date': '27-Feb-18, 10:11:50', 'method': 'column2_gradient14min.M', 'instrument': 'Asterix ChemStation', 'unit': 'mAU', 'signal': 'DAD1B, Sig=280.0,4.0  Ref=off'}

   --------
   ADC1A.CH
   -------- 
   ...

The numpy arrays holding numerical data can be accessed using the :code:`xlabels`, :code:`ylabels`, and :code:`data` attributes of a DataFile. 

.. code-block:: python

   times = datafile.xlabels 
   wavelengths = datafile.ylabels
   absorbances = datafile.data

For a full list of user options, view the :ref:`documentation <api>` for the DataFile and DataDirectory classes.