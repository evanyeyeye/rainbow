.. _examples:

Example Snippets
================

This page contains basic snippets for common tasks using **rainbow**. 

Exporting data to csv 
---------------------

The following code exports the data from every binary file in a directory named violet.raw. 

Waters .raw directories may contain miscellaneous analog data without a detector, like system pressure. These are not included in the :code:`datafiles` attribute. Thus, we use :code:`by_name` instead.

.. code-block:: python

   import rainbow as rb
   import os

   datadir = rb.read("violet.raw")
   for name in datadir.by_name:
       csv_name = os.path.splitext(name)[0] + ".csv"
       datadir.export_csv(name, csv_name)

Processing a dataset
--------------------

Suppose we have a directory MY_DATASET that contains hundreds of Agilent .D subdirectories. The directory structure might look something like:

.. code-block:: bash 
    
   MY_DATASET 
       |- A1.D 
       |- A2.D 
       |- A3.D
       |- ...

The following code reads every subdirectory in MY_DATASET using multiprocessing
for faster speed. The resulting variable :code:`datadirs` is a list of
DataDirectory objects.

The :code:`if __name__ == "__main__"` guard is not optional. On macOS and
Windows a worker process starts by re-importing the module that created the
pool, so without the guard each worker creates its own pool, and so on until the
machine gives out.

.. code-block:: python

   import rainbow as rb
   import multiprocessing as mp
   import os

   DATASET = "MY_DATASET"

   if __name__ == "__main__":
       dirpaths = [os.path.join(DATASET, name)
                   for name in os.listdir(DATASET) if name != ".DS_Store"]

       with mp.Pool() as pool:
           datadirs = pool.map(rb.read, dirpaths)