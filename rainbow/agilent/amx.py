"""
Read an Agilent OpenLab CDS acquisition method (.amx).

An .amx is an Open Packaging Conventions (zip) package, like a .docx::

    [Content_Types].xml, _rels/.rels      the package's own parts
    package/services/metadata/core-properties/<id>.psmdcp
                                          title, version, created, modified
    Agilent/MethodType                    "AcquisitionMethod" (UTF-16)
    Agilent/ReportableInformation         the method as ACAML: one Section
                                          per module, each Parameter with
                                          its name, ID, value and unit
    DeviceMethodSettings/<driver>%231     one part per module, named for its
                                          driver (AgilentPumpDriver,
                                          Agilent1200erDadDriver, ...): the
                                          settings as the driver keeps them
    MethodProperties/MethodProperties     technique (LC, GC) and run time
    SchemaVersion/SchemaVersion
    *.chk                                 SHA-1 of the part beside it

The settings are read from ``ReportableInformation``, the method as OpenLab
reports it: the same ACAML a ChemStation .D keeps as ``acq.macaml``, with each
value in the unit it states. The driver parts keep some values as codes: in
every method read so far, the DAD part's ``<Slitwidth>2`` is reported as
``4 nm``, its ``<Peakwidth>4`` as ``> 0.1 min (2 s response time) (2.5 Hz)``,
and its analog attenuation ``10`` as ``1000 mAU``; and no driver part states a
unit. So the driver parts are read for which modules the method drives (the
driver's name and the module type it records), and the report for what each
is set to.

What a module's report section states is read by its driver's table in
:data:`MODULES`: the ACAML parameter IDs read, each to the field it is
stated as. A module whose driver has no table is listed (name, model,
driver) with no settings. A value the report leaves empty, or writes as
``---`` (a timetable row that does not change it), is not stated.

"""
import os
import posixpath
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

from rainbow.agilent import acaml

# The report's timing rows, which each module's section carries.
_TIMES = {
    'StopTime_StopTimeMode': 'stop_time_mode',
    'StopTime_StopTimeValue': 'stop_time',
    'PostTime_PostTimeMode': 'post_time_mode',
    'PostTime_PostTimeValue': 'post_time',
}

# One table per module driver, keyed by the driver's name as its part is
# named (DeviceMethodSettings/<driver>%231). In each:
#
#   settings   parameter ID -> field, for the section's parameters outside
#              a table (in its sub-sections too)
#   tables     table name -> {parameter ID -> field}: each of the section's
#              tables whose rows hold any of those IDs is stated under that
#              name, one dict per row, in the report's order
#   run        run-level key -> field: what the module states that rainbow
#              states for a whole run (as a .D's acq.macaml gives it)
#
# Adding a module is adding its driver's table here. An LC/MSD's driver part
# would be entered here too once an OpenLab LC/MS method is at hand: no public
# method so far names the MSD's driver part or the IDs of its report section.
MODULES = {
    'AgilentPumpDriver': {
        'settings': dict(_TIMES, **{
            'Flow': 'flow_rate',
            'LowPressureLimit': 'low_pressure_limit',
            'HighPressureLimit': 'high_pressure_limit',
            'MaximumFlowRamp': 'max_flow_ramp_up',
            'FlowRampDown': 'max_flow_ramp_down',
        }),
        'tables': {
            'solvents': {
                'SolventComposition_Channel': 'channel',
                'SolventComposition_Channel1ExtendedSolventType_Parameter':
                    'solvent',
                'SolventComposition_Channel1UserName': 'name',
                'SolventComposition_Used': 'used',
                'SolventComposition_Percentage': 'percent',
            },
            'timetable': {
                'Time': 'time',
                'PercentA': 'percent_a',
                'PercentB': 'percent_b',
                'PercentC': 'percent_c',
                'PercentD': 'percent_d',
                'Flow_DisplayValue': 'flow_rate',
                'HighPressureLimit_DisplayValue': 'high_pressure_limit',
            },
        },
        'run': {'flow_rate': 'flow_rate', 'run_time': 'stop_time'},
    },
    'Agilent1200erDadDriver': {
        'settings': dict(_TIMES, **{
            'Peakwidth': 'peak_width',
            'Slitwidth': 'slit_width',
            'SpectraAcquisition_SpectraRangeFrom': 'spectrum_from',
            'SpectraAcquisition_SpectraRangeTo': 'spectrum_to',
            'SpectraAcquisition_SpectraStep': 'spectrum_step',
            'SpectraAcquisition_SpectraAcqMode': 'spectrum_store',
        }),
        'tables': {
            'signals': {
                'Signals_Signal_ID': 'signal',
                'Signals_Signal_UseSignal': 'acquire',
                'Signals_Signal_Wavelength': 'wavelength',
                'Signals_Signal_Bandwidth': 'bandwidth',
                'Signals_Signal_UseReference': 'use_reference',
            },
        },
        'run': {},
    },
    'AgilentColumnCompDriver': {
        'settings': dict(_TIMES, **{
            'LeftTemperatureControl_TemperatureControlMode':
                'left_temperature_mode',
            'LeftTemperatureControl_Temperature': 'left_temperature',
            'RightTemperatureControl_TemperatureControlMode':
                'right_temperature_mode',
            'RightTemperatureControl_Temperature': 'right_temperature',
        }),
        'tables': {},
        # As for a .D: the left temperature, where it is controlled.
        'run': {'column_temperature': 'left_temperature'},
    },
    'AgilentSamplerDriver': {
        'settings': dict(_TIMES, **{
            'Injection_InjectionVolume': 'injection_volume',
            'SamplingSpeed_DrawSpeed': 'draw_speed',
            'SamplingSpeed_EjectSpeed': 'eject_speed',
            'SamplingSpeed_WaitTimeAfterDrawing': 'wait_after_drawing',
            'Injection_NeedleWashMode': 'needle_wash_mode',
        }),
        'tables': {},
        'run': {'injection_volume': 'injection_volume'},
    },
}

# The report's Method Information rows, stated under acq_method_info.
_METHOD_INFO = {
    'ID_Method_Version': 'version',
    'ID_Method_Created': 'created',
    'ID_Method_CreatedBy': 'created_by',
    'ID_Method_Modified': 'modified',
    'ID_Method_ModifiedBy': 'modified_by',
    'ID_Method_ApprovalState': 'status',
    'ID_Method_Description': 'description',
}

_REPORT = 'Agilent/ReportableInformation'
_PROPERTIES = 'MethodProperties/MethodProperties'
_DRIVER_DIR = 'DeviceMethodSettings/'

# A driver part's name, once unquoted: "AgilentPumpDriver#1".
_DRIVER_RE = re.compile(r'^(?P<driver>[^#]+)#(?P<instance>\d+)$')

# What the report writes for a value a timetable row leaves unchanged.
_UNCHANGED = '---'


def find(path):
    """
    The acquisition method in a folder: the .amx named after the folder, else
    its only .amx; None when it holds none, or several and none named after
    it.

    Args:
        path (str): A run's folder (a .sirslt, or a .D).

    Returns:
        str or None: The .amx's path.

    """
    try:
        names = sorted(name for name in os.listdir(path)
                       if name.lower().endswith('.amx')
                       and os.path.isfile(os.path.join(path, name)))
    except OSError:
        return None
    stem = os.path.splitext(os.path.basename(os.path.normpath(path)))[0]
    named = [name for name in names if os.path.splitext(name)[0] == stem]
    chosen = named or names
    return os.path.join(path, chosen[0]) if len(chosen) == 1 else None


def read(path):
    """
    Reads an OpenLab CDS acquisition method (.amx).

    Args:
        path (str): Path of the .amx file.

    Returns:
        dict: What the method states, in the keys a .D's acq.macaml is
        stated in, any of:

        - ``acq_method``: the method's file name, from the path it was last
          saved as (the directory is not stated);
        - ``acq_method_info``: its ``version``, ``created``, ``created_by``,
          ``modified``, ``modified_by``, ``status`` and ``description``;
        - ``technique``: ``'LC'`` or ``'GC'``;
        - ``modules``: ``{"name", "model"}`` per module, in the method's
          order;
        - ``injection_volume``, ``flow_rate``, ``column_temperature``,
          ``run_time``: as :func:`rainbow.agilent.method.parse_injection_metadata`
          states them for a .D;
        - ``module_settings``: per module, in the method's order,
          ``{"name", "model", "driver", "settings"}``, ``settings`` holding
          the fields its driver's table in :data:`MODULES` reads.

        A quantity is ``{"value": float, "unit": str}`` in the unit the report
        states; a Yes/No setting is a bool; any other value is stated as its
        text (``slit_width`` ``'4 nm'``, a timetable's first ``time``
        ``'Start. Cond.'``).

    Raises:
        zipfile.BadZipFile: ``path`` is not a zip package.

    """
    with zipfile.ZipFile(path) as package:
        names = set(package.namelist())
        report = _xml(package, _REPORT, names)
        properties = _xml(package, _PROPERTIES, names)
        drivers = _drivers(package, names)
    out = {}
    if report is not None:
        sections = acaml.sections(report)
        out.update(_method_info(sections))
    technique = _technique(properties)
    if technique:
        out['technique'] = technique
    if report is not None:
        modules = _modules(sections, drivers)
        if modules:
            out['modules'] = [{'name': module['name'],
                               'model': module['model']}
                              for module in modules]
            for module in modules:
                table = MODULES.get(module['driver'], {})
                for key, field in table.get('run', {}).items():
                    value = module.get('settings', {}).get(field)
                    if isinstance(value, dict):
                        out.setdefault(key, value)
            out['module_settings'] = modules
    return out


def read_run(path):
    """
    What the acquisition method in a run's folder states (:func:`find`,
    :func:`read`): {} when the folder holds none, or one that cannot be read.
    """
    found = find(path)
    if found is None:
        return {}
    try:
        return read(found)
    except (zipfile.BadZipFile, ET.ParseError, ValueError, LookupError,
            OSError, KeyError):
        # A method that cannot be read contributes nothing, as any other
        # sidecar of a run does.
        return {}


def _xml(package, name, names):
    """A part of the package, parsed, or None when it is absent."""
    if name not in names:
        return None
    return ET.fromstring(package.read(name))


def _drivers(package, names):
    """
    The driver parts: {(module type, instance): driver name}, from the part
    names (DeviceMethodSettings/AgilentPumpDriver%25231 is
    "AgilentPumpDriver#1", its name percent-encoded twice) and the
    ModuleType each part's root records.
    """
    found = {}
    for name in sorted(names):
        if not name.startswith(_DRIVER_DIR) or name.endswith('.chk'):
            continue
        part = posixpath.basename(name)
        for _ in range(2):
            part = urllib.parse.unquote(part)
        match = _DRIVER_RE.match(part)
        if not match:
            continue
        root = ET.fromstring(package.read(name))
        model = (root.get('ModuleType') or '').strip()
        if model:
            found[(model, match.group('instance'))] = match.group('driver')
    return found


def _technique(properties):
    """MethodProperties' <InstrumentTechnique>, where it is LC or GC."""
    if properties is None:
        return None
    for element in properties.iter():
        if element.tag.rsplit('}', 1)[-1] == 'InstrumentTechnique':
            text = (element.text or '').strip().upper()
            return text if text in ('LC', 'GC') else None
    return None


def _method_info(sections):
    """acq_method and acq_method_info, from the Method Information rows."""
    out, info = {}, {}
    for section in sections:
        if section.get('id') != 'Method_Information':
            continue
        for parameter in section['parameters']:
            value = (parameter.get('value') or '').strip()
            if not value:
                continue
            if parameter.get('id') == 'ID_Method_Original':
                out['acq_method'] = value.replace('\\', '/').rsplit('/', 1)[-1]
            elif parameter.get('id') in _METHOD_INFO:
                info[_METHOD_INFO[parameter['id']]] = value
    if info:
        out['acq_method_info'] = info
    return out


def _modules(sections, drivers):
    """
    One entry per module section of the report (a section stating its
    ModuleType), in its order, with what its driver's table reads.
    """
    modules = []
    for section in sections:
        own = {parameter.get('id'): (parameter.get('value') or '').strip()
               for parameter in section['parameters']}
        model = own.get('ModuleType')
        if not model:
            continue
        module = {'name': own.get('ModuleDisplayName') or None,
                  'model': model,
                  'driver': _driver_of(drivers, model, own.get('Order'))}
        module = {key: value for key, value in module.items() if value}
        table = MODULES.get(module.get('driver'))
        if table:
            settings = _settings(section, table)
            if settings:
                module['settings'] = settings
        modules.append(module)
    return modules


def _driver_of(drivers, model, order):
    """The driver of a module: by its type and order, else by its type alone
    where one driver part records that type."""
    if (model, order) in drivers:
        return drivers[(model, order)]
    of_type = [driver for (kind, _), driver in drivers.items()
               if kind == model]
    return of_type[0] if len(of_type) == 1 else None


def _settings(section, table):
    """What a module's section states, read by its driver's table."""
    settings = {}
    for parameter in _parameters(section):
        field = table['settings'].get(parameter.get('id'))
        if field and field not in settings:
            value = _value(parameter)
            if value is not None:
                settings[field] = value
    for name, fields in table['tables'].items():
        rows = []
        for found in _tables(section):
            for row in found['rows']:
                if not any(p.get('id') in fields for p in row):
                    continue
                entry = {}
                for parameter in row:
                    field = fields.get(parameter.get('id'))
                    value = _value(parameter) if field else None
                    if value is not None:
                        entry[field] = value
                rows.append(entry)
        if rows:
            settings[name] = rows
    return settings


def _parameters(section):
    """A section's parameters outside its tables, its sub-sections' too."""
    for parameter in section['parameters']:
        yield parameter
    for sub in section['sections']:
        for parameter in _parameters(sub):
            yield parameter


def _tables(section):
    """A section's tables, its sub-sections' too."""
    for table in section['tables']:
        yield table
    for sub in section['sections']:
        for table in _tables(sub):
            yield table


def _value(parameter):
    """
    A report value as stated: a number with its unit as a quantity, Yes/No
    as a bool, anything else as its text; None when empty or ``---``.
    """
    text = (parameter.get('value') or '').strip()
    if not text or text == _UNCHANGED:
        return None
    unit = (parameter.get('unit') or '').strip()
    if text in ('Yes', 'No'):
        return text == 'Yes'
    try:
        number = float(text)
    except ValueError:
        return text
    if unit:
        return {'value': number, 'unit': unit}
    return int(number) if number.is_integer() and '.' not in text else number
