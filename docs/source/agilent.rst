Agilent (.D)
============

Agilent directories are distinguished by the .D extension. OpenLab CDS 2.x
exports instead use a single :ref:`.dx archive <dx>`.

**rainbow** can parse the following Agilent binary formats:

.. toctree::
   :maxdepth: 1

   Agilent .uv <agilent/uv>
   Agilent .ms <agilent/ms>
   Agilent .ch (FID) <agilent/ch_fid>
   Agilent .ch (other) <agilent/ch_other>
   Agilent MSProfile.bin <agilent/hrms>
   Agilent ICP-MS MSProfile.bin <agilent/icpms>
   Agilent OpenLab CDS (.dx) <agilent/dx>

It may be useful to search for a binary format by detector. 

.. role:: raw-html(raw)
    :format: html

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Detector
     - Formats
   * - UV
     - :doc:`Agilent .uv <agilent/uv>` :raw-html:`<br/>`
       :doc:`Agilent .ch (other) <agilent/ch_other>` :raw-html:`<br/>`
       :doc:`Agilent OpenLab CDS (.dx) <agilent/dx>`
   * - MS
     - :doc:`Agilent .ms <agilent/ms>`
   * - FID 
     - :doc:`Agilent .ch (FID) <agilent/ch_fid>`
   * - CAD 
     - :doc:`Agilent .ch (other) <agilent/ch_other>`
   * - ELSD
     - :doc:`Agilent .ch (other) <agilent/ch_other>`
   * - HRMS
     - :doc:`Agilent MSProfile.bin <agilent/hrms>`
   * - ICP-MS
     - :doc:`Agilent ICP-MS MSProfile.bin <agilent/icpms>`
