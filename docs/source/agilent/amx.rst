.. _amx:

Agilent OpenLab CDS Acquisition Method (.amx)
=============================================

OpenLab CDS 2.x saves an acquisition method as an :code:`.amx` file, and
writes a copy of it into each :ref:`.sirslt result folder <sirslt>` it
acquires with. The file is an Open Packaging Conventions (zip) package, like a
.docx:

.. list-table::
   :widths: 40 60
   :header-rows: 1

   * - Part
     - Information
   * - ``Agilent/ReportableInformation``
     - The method as ACAML, the same document a ChemStation .D keeps as
       ``acq.macaml``: the method's name, version and dates, then one
       ``Section`` per module, each ``Parameter`` with its name, ID, value
       and unit. **rainbow** reads the settings from here.
   * - ``DeviceMethodSettings/<driver>%25231``
     - One part per module, named for its driver (``AgilentPumpDriver``,
       ``Agilent1200erDadDriver``, ``AgilentColumnCompDriver``,
       ``AgilentSamplerDriver``, ``AgilentFractionCollectorDriver``): the
       settings as the driver keeps them, and the module's configuration.
       **rainbow** reads which driver each module has and the module type it
       records.
   * - ``MethodProperties/MethodProperties``
     - The technique (``LC``) and the run time in seconds.
   * - ``Agilent/MethodType``, ``Agilent/ApprovalState``,
       ``SchemaVersion/SchemaVersion``, ``Agilent/AuditTrail*``,
       ``package/services/metadata/core-properties/*.psmdcp``
     - The method type, approval state, schema version, audit trail and
       package properties.
   * - ``*.chk``
     - The SHA-1 of the part beside it.

The driver parts state no units, and keep some values as codes: in every
method read so far the DAD part's ``<Slitwidth>2`` is reported as ``4 nm``,
its ``<Peakwidth>4`` as ``> 0.1 min (2 s response time) (2.5 Hz)``, and its
analog attenuation ``10`` as ``1000 mAU``. So each value is read from the
report, in the unit the report states.

Reading a method
----------------

:func:`rainbow.agilent.amx.read` reads a lone method. A .sirslt folder's
method is read by :code:`rb.read` and :code:`rb.read_metadata` alike, in the
same keys::

    from rainbow.agilent import amx
    method = amx.read("path/to/method.amx")
    method['injection_volume']   # {'value': 1.0, 'unit': 'µL'}

    import rainbow as rb
    rb.read("path/to/run.sirslt").metadata['flow_rate']

The keys a .D's ``acq.macaml`` gives are given the same way:
``injection_volume`` (the sampler's), ``flow_rate`` and ``run_time`` (the
pump's flow and stop time), ``column_temperature`` (the left temperature,
where the compartment controls it), ``modules`` (each module's name and
model), and ``acq_method`` (the file name it was last saved as). Besides
them, ``acq_method_info`` holds the method's version, dates and status, and
``module_settings`` holds, per module, its ``name``, ``model``, ``driver``
and ``settings``:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Driver
     - Settings
   * - ``AgilentPumpDriver``
     - ``flow_rate``, pressure limits, flow ramps, stop and post time;
       ``solvents`` (channel, solvent, used, percent) and ``timetable``
       (time, percent A to D, flow, pressure limit), one dict per row
   * - ``Agilent1200erDadDriver``
     - ``signals`` (signal, acquire, wavelength, bandwidth, use_reference),
       ``peak_width``, ``slit_width``, spectrum range, step and store mode
   * - ``AgilentColumnCompDriver``
     - left and right temperature and their control modes
   * - ``AgilentSamplerDriver``
     - ``injection_volume``, draw and eject speed, wait after drawing,
       needle wash mode

A quantity is ``{'value': float, 'unit': str}``, Yes/No a bool, and anything
else the report's text: ``slit_width`` is ``'4 nm'``, and a timetable's first
row, the starting conditions, has ``time`` ``'Start. Cond.'``. A value the
report leaves empty, or writes as ``---`` (a timetable row that does not
change it), is not stated; a column compartment that is not controlled states
no temperature. A module whose driver has no entry (the fraction collector)
is listed with no settings.

Each driver's entry in :data:`rainbow.agilent.amx.MODULES` lists the report
parameter IDs it reads and the field each is stated as, so reading another
module is adding its entry. An LC/MSD's entry goes there too, once an OpenLab
LC/MS method is at hand: no public method so far names the MSD's driver part
or its report parameters.
