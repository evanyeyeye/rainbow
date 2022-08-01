Waters (.raw)
=============

Waters directories are distinguished by the .raw extension. 

**rainbow** can parse the following Waters binary formats:

.. toctree::
   :maxdepth: 1

   Waters FUNC .IDX <waters/funcidx>
   Waters FUNC .DAT (2-byte) <waters/funcdat2>
   Waters FUNC .DAT (6-byte) <waters/funcdat6>
   Waters FUNC .DAT (8-byte) <waters/funcdat8>
   Waters CHRO .DAT <waters/chrodat>

It may be useful to search for a binary format by detector. 

.. role:: raw-html(raw)
    :format: html

.. list-table::
   :widths: 30 70
   :header-rows: 1
   
   * - Detector
     - Formats
   * - UV
     - :doc:`Waters CHRO .DAT <waters/chrodat>` :raw-html:`<br/>`
       :doc:`Waters FUNC .IDX <waters/funcidx>` :raw-html:`<br/>`
       :doc:`Waters FUNC .DAT (6-byte) <waters/funcdat6>`
   * - MS 
     - :doc:`Waters FUNC .IDX <waters/funcidx>` :raw-html:`<br/>`
       :doc:`Waters FUNC .DAT (2-byte) <waters/funcdat2>` :raw-html:`<br/>`
       :doc:`Waters FUNC .DAT (6-byte) <waters/funcdat6>` :raw-html:`<br/>`
       :doc:`Waters FUNC .DAT (8-byte) <waters/funcdat8>`
   * - CAD 
     - :doc:`Waters CHRO .DAT <waters/chrodat>`
   * - ELSD
     - :doc:`Waters CHRO .DAT <waters/chrodat>`