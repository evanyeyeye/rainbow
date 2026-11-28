"""
Tests for Agilent OpenLab CDS acquisition methods (.amx).

Four real methods from one HPLC (fraction collector G1364F, quaternary pump
G7104C, DAD G7115A, column compartment G7116A, multisampler G7167A), CC0
from chromConverterExtraTests, anonymised (see tests/inputs/README_sirslt.md):

- date.amx: a gradient with flow changes in its timetable;
- pear.amx: a gradient at one flow, 40 °C, 5 µL;
- kiwi.amx: no timetable, oven not controlled, one DAD signal, no spectrum;
- fig.sirslt/fig.amx: the method of the run in that folder.

Five from a UHPLC with an LC/MSD iQ single quad, shared by p3bm in #82
(see tests/inputs/README_sirslt.md), four of them with their runs:

- jade.sirslt: one SIM/Scan time segment, a scan and one SIM ion;
- ochre.sirslt: two SIM/Scan time segments, each its own SIM ion;
- rose.sirslt: positive and negative scans, the negative on a fragmentor
  ramp;
- coral.sirslt: no single quad; a DAD signal with a reference wavelength;
- mango.amx: a method alone, its single quad set to Scan.

Each expected value is the one the method's Agilent/ReportableInformation
part states.

"""
import os
import zipfile

import pytest

import rainbow as rb
from rainbow.agilent import amx

INPUTS = os.path.join("tests", "inputs")
FLOW = os.path.join(INPUTS, "date.amx")
GLUCOSINOLATES = os.path.join(INPUTS, "pear.amx")
STORAGE = os.path.join(INPUTS, "kiwi.amx")
RUN = os.path.join(INPUTS, "fig.sirslt")
SIMPLE = os.path.join(RUN, "fig.amx")
OLIVE = os.path.join(INPUTS, "olive.sirslt")
PLUM = os.path.join(INPUTS, "plum.sirslt")
LIME = os.path.join(INPUTS, "lime.sirslt")
SCAN = os.path.join(INPUTS, "mango.amx")
JADE = os.path.join(INPUTS, "jade.sirslt")
OCHRE = os.path.join(INPUTS, "ochre.sirslt")
ROSE = os.path.join(INPUTS, "rose.sirslt")
CORAL = os.path.join(INPUTS, "coral.sirslt")
SIM_SCAN = os.path.join(JADE, "example_MS_with_SIM.amx")
SEGMENTS = os.path.join(OCHRE, "example_MS_with_time_segments.amx")
POS_NEG = os.path.join(ROSE, "example_MS_pos_and_neg.amx")
DAD_REF = os.path.join(CORAL, "example_DAD_ref.amx")

# What an .amx adds to a run's metadata.
AMX_KEYS = ('acq_method', 'acq_method_info', 'modules', 'module_settings',
            'injection_volume', 'flow_rate', 'column_temperature', 'run_time')

MODULES = [{'name': 'Fraction Collector', 'model': 'G1364F'},
           {'name': 'Quat. Pump', 'model': 'G7104C'},
           {'name': 'DAD', 'model': 'G7115A'},
           {'name': 'Column Comp.', 'model': 'G7116A'},
           {'name': 'Multisampler', 'model': 'G7167A'}]


def q(value, unit):
    return {'value': value, 'unit': unit}


def _module(method, driver):
    found = [module for module in method['module_settings']
             if module.get('driver') == driver]
    assert len(found) == 1
    return found[0]


@pytest.mark.parametrize("path, name, run_time, flow, temperature, volume", [
    (FLOW, 'date.amx', 16.0, 0.4, 25.0, 1.0),
    (GLUCOSINOLATES, 'pear.amx', 31.0, 1.0, 40.0, 5.0),
    (STORAGE, 'kiwi.amx', 15.0, 1.0, None, 0.0),
    (SIMPLE, 'fig.amx', 10.0, 0.4, 25.0, 1.0),
])
def test_the_run_settings_a_d_states(path, name, run_time, flow,
                                     temperature, volume):
    method = amx.read(path)
    # The file name of the path it was last saved as.
    assert method['acq_method'] == name
    assert method['technique'] == 'LC'
    assert method['modules'] == MODULES
    assert method['run_time'] == q(run_time, 'min')
    assert method['flow_rate'] == q(flow, 'mL/min')
    assert method['injection_volume'] == q(volume, 'µL')
    if temperature is None:
        # "Not Controlled": no temperature is stated.
        assert 'column_temperature' not in method
    else:
        assert method['column_temperature'] == q(temperature, '°C')


def test_the_method_information():
    assert amx.read(FLOW)['acq_method_info'] == {
        'version': '2026-0524-2107-26472',
        'created': '2026-05-24 16:06:42-05:00',
        'created_by': 'SYSTEM (SYSTEM)',
        'modified': '2026-05-24 16:07:26-05:00',
        'modified_by': 'SYSTEM (SYSTEM)',
        'status': 'Generic',
    }


def test_each_module_names_its_driver():
    drivers = [module.get('driver')
               for module in amx.read(FLOW)['module_settings']]
    assert drivers == ['AgilentFractionCollectorDriver', 'AgilentPumpDriver',
                       'Agilent1200erDadDriver', 'AgilentColumnCompDriver',
                       'AgilentSamplerDriver']


def test_a_module_without_a_table_states_no_settings():
    collector = _module(amx.read(FLOW), 'AgilentFractionCollectorDriver')
    assert collector == {'name': 'Fraction Collector', 'model': 'G1364F',
                         'driver': 'AgilentFractionCollectorDriver'}


def test_the_dad_settings():
    dad = _module(amx.read(FLOW), 'Agilent1200erDadDriver')['settings']
    # As the report states them: the driver part keeps the slit as the code
    # 2 and the peak width as 4.
    assert dad['slit_width'] == '4 nm'
    assert dad['peak_width'] == '> 0.1 min (2 s response time) (2.5 Hz)'
    assert dad['spectrum_from'] == q(190.0, 'nm')
    assert dad['spectrum_to'] == q(400.0, 'nm')
    assert dad['spectrum_step'] == q(2.0, 'nm')
    assert dad['spectrum_store'] == 'All'
    signals = dad['signals']
    assert [s['signal'] for s in signals] == \
        ['Signal ' + letter for letter in 'ABCDEFGH']
    assert [s['wavelength']['value'] for s in signals if s['acquire']] == \
        [229.0, 200.0, 260.0, 360.0]
    assert signals[0] == {'signal': 'Signal A', 'acquire': True,
                          'wavelength': q(229.0, 'nm'),
                          'bandwidth': q(4.0, 'nm'), 'use_reference': False}
    # A signal not acquired states nothing else.
    assert signals[4] == {'signal': 'Signal E', 'acquire': False}


def test_a_dad_storing_no_spectrum_states_no_range():
    dad = _module(amx.read(STORAGE), 'Agilent1200erDadDriver')['settings']
    assert dad['spectrum_store'] == 'None'
    for key in ('spectrum_from', 'spectrum_to', 'spectrum_step'):
        assert key not in dad
    assert [s['wavelength'] for s in dad['signals'] if s['acquire']] == \
        [q(250.0, 'nm')]


def test_the_pump_settings():
    pump = _module(amx.read(FLOW), 'AgilentPumpDriver')['settings']
    assert pump['flow_rate'] == q(0.4, 'mL/min')
    assert pump['stop_time'] == q(16.0, 'min')
    assert pump['post_time'] == q(3.0, 'min')
    assert pump['high_pressure_limit'] == q(800.0, 'bar')
    assert pump['low_pressure_limit'] == q(0.0, 'bar')
    assert pump['max_flow_ramp_up'] == q(100.0, 'mL/min²')
    assert pump['solvents'] == [
        {'channel': 'A', 'solvent': '100.0 % Water V.03', 'used': True,
         'percent': q(99.9, '%')},
        {'channel': 'B', 'solvent': '100.0 % Acetonitrile V.03',
         'used': True, 'percent': q(0.1, '%')},
        {'channel': 'C', 'used': False},
        {'channel': 'D', 'used': False},
    ]


def test_the_pump_timetable():
    timetable = _module(amx.read(FLOW), 'AgilentPumpDriver')['settings'][
        'timetable']
    # The report's first row is the starting conditions, its time in words.
    assert timetable[0]['time'] == 'Start. Cond.'
    assert timetable[0]['flow_rate'] == q(0.4, 'mL/min')
    assert [row['time']['value'] for row in timetable[1:]] == \
        [3.0, 5.0, 6.0, 10.0, 11.0, 13.0, 14.0, 15.0, 16.0]
    assert [row['percent_b']['value'] for row in timetable] == \
        [0.1, 8.0, 8.0, 31.0, 31.0, 60.0, 60.0, 92.0, 92.0, 0.1]
    assert [row.get('flow_rate', {}).get('value') for row in timetable] == \
        [0.4, 0.5, 0.5, 0.5, 0.55, 0.55, 0.6, 0.6, 0.7, None]
    # "---" (unchanged) is not stated.
    assert 'high_pressure_limit' not in timetable[1]


def test_a_flow_the_timetable_leaves_unchanged_is_not_stated():
    timetable = _module(amx.read(GLUCOSINOLATES), 'AgilentPumpDriver')[
        'settings']['timetable']
    assert timetable[0]['flow_rate'] == q(1.0, 'mL/min')
    assert all('flow_rate' not in row for row in timetable[1:])
    assert timetable[-1]['time'] == q(31.0, 'min')


def test_a_method_with_no_timetable_states_none():
    pump = _module(amx.read(STORAGE), 'AgilentPumpDriver')['settings']
    assert 'timetable' not in pump
    assert 'post_time' not in pump
    assert pump['post_time_mode'] == 'Off'


def test_the_column_compartment_settings():
    oven = _module(amx.read(GLUCOSINOLATES), 'AgilentColumnCompDriver')[
        'settings']
    assert oven['left_temperature'] == q(40.0, '°C')
    assert oven['right_temperature'] == q(40.0, '°C')
    assert oven['left_temperature_mode'] == 'Temperature Set'
    assert oven['post_time'] == q(6.0, 'min')
    idle = _module(amx.read(STORAGE), 'AgilentColumnCompDriver')['settings']
    assert idle['left_temperature_mode'] == 'Not Controlled'
    assert 'left_temperature' not in idle


def test_the_sampler_settings():
    sampler = _module(amx.read(FLOW), 'AgilentSamplerDriver')['settings']
    assert sampler['injection_volume'] == q(1.0, 'µL')
    assert sampler['draw_speed'] == q(100.0, 'µL/min')
    assert sampler['eject_speed'] == q(400.0, 'µL/min')
    assert sampler['wait_after_drawing'] == q(1.2, 's')
    assert sampler['needle_wash_mode'] == 'Standard Wash'


def test_a_file_that_is_not_a_package_raises(tmp_path):
    path = tmp_path / "broken.amx"
    path.write_bytes(b"not a zip")
    with pytest.raises(zipfile.BadZipFile):
        amx.read(str(path))


def test_a_package_without_the_report_states_its_technique_alone(tmp_path):
    # The settings are the report's: without it, none are stated.
    path = tmp_path / "bare.amx"
    with zipfile.ZipFile(FLOW) as source, zipfile.ZipFile(path, "w") as out:
        for name in source.namelist():
            if name != "Agilent/ReportableInformation":
                out.writestr(name, source.read(name))
    assert amx.read(str(path)) == {'technique': 'LC'}


# --- in a run ---------------------------------------------------------------

def test_a_sirslt_states_its_method():
    metadata = rb.read(RUN).metadata
    method = amx.read(SIMPLE)
    for key in AMX_KEYS:
        assert metadata[key] == method[key]
    # The technique the .acaml states stays.
    assert metadata['technique'] == 'LC'


def test_read_metadata_states_what_read_states():
    assert rb.read_metadata(RUN)['metadata'] == rb.read(RUN).metadata


@pytest.mark.parametrize("folder", [OLIVE, PLUM, LIME])
def test_a_run_without_an_amx_states_none_of_it(folder):
    assert amx.find(folder) is None
    metadata = rb.read(folder).metadata
    for key in ('acq_method', 'acq_method_info', 'module_settings'):
        assert key not in metadata
    assert rb.read_metadata(folder)['metadata'] == metadata


def test_find_takes_the_amx_named_after_the_folder(tmp_path):
    folder = tmp_path / "run.sirslt"
    folder.mkdir()
    (folder / "other.amx").write_bytes(b"")
    assert amx.find(str(folder)) == str(folder / "other.amx")
    (folder / "second.amx").write_bytes(b"")
    # Two, neither named after the folder: neither is the run's.
    assert amx.find(str(folder)) is None
    (folder / "run.amx").write_bytes(b"")
    assert amx.find(str(folder)) == str(folder / "run.amx")


def test_an_unreadable_amx_in_a_run_states_nothing(tmp_path):
    folder = tmp_path / "run.sirslt"
    folder.mkdir()
    (folder / "run.amx").write_bytes(b"not a zip")
    assert amx.read_run(str(folder)) == {}


SQ_MODULES = [{'name': 'SQ Mass Spectrometer', 'model': 'LC/MSD iQ'},
              {'name': 'Binary Pump', 'model': 'G7120A'},
              {'name': 'Column Comp.', 'model': 'G7116B'},
              {'name': 'DAD', 'model': 'G7117A'},
              {'name': 'Sampler', 'model': 'G7129B'}]


@pytest.mark.parametrize("path, name", [
    (SIM_SCAN, 'example_MS_with_SIM.amx'),
    (SCAN, 'BEH_Acidic_6min.amx'),
    (SEGMENTS, 'example_MS_with_time_segments.amx'),
    (POS_NEG, 'example_MS_pos_and_neg.amx'),
])
def test_a_method_with_a_single_quad_reads(path, name):
    """The single quad's driver part records its model as <msModel>, not
    ModuleType: the method still reads, each module with its driver."""
    method = amx.read(path)
    assert method['acq_method'] == name
    assert method['modules'] == SQ_MODULES
    assert [m.get('driver') for m in method['module_settings']] == [
        'LCSQ', 'AgilentPumpDriver', 'AgilentColumnCompDriver',
        'Agilent1200erDadDriver', 'AgilentSamplerDriver']
    assert method['run_time'] == q(6.0, 'min')


def test_the_single_quads_settings():
    sq = _module(amx.read(SIM_SCAN), 'LCSQ')['settings']
    assert sq['ion_source'] == 'ESI'
    assert sq['tune_file'] == 'atunes.tune'
    assert sq['sim_percent'] == q(50.0, '%')
    assert [row['value'] for row in sq['timetable']] == ['To MS', 'To Waste']
    [segment] = sq['time_segments']
    assert segment['time'] == q(0.0, 'min')
    assert segment['scan_type'] == 'SIM/Scan'
    # The report keeps the scan row and the SIM ion in one table: each is
    # told by its first ID (StartMass, Mass).
    assert segment['scan_parameters'] == [{
        'mz_low': q(100.0, 'm/z'), 'mz_high': q(1000.0, 'm/z'),
        'scan_time': q(580.0, 'ms'), 'gain_factor': 1,
        'fragmentor': q(110.0, 'V'), 'polarity': '+', 'threshold': 0,
        'data_storage': 'Centroid', 'ionization_mode': 'ESI'}]
    assert segment['monitored_ions'] == [{
        'compound': 'Caffeine', 'mz': q(295.0, 'm/z'),
        'dwell': q(580.0, 'ms'), 'gain_factor': 1,
        'fragmentor': q(100.0, 'V'), 'polarity': '+',
        'ionization_mode': 'ESI'}]
    assert segment['source'][0] == {'parameter': 'Gas Temperature (°C)',
                                    'positive': 325, 'negative': 325}


def test_each_time_segment_states_its_own_rows():
    """Segment 2 lists its SIM ion before its scan row; each segment keeps
    its own."""
    segments = _module(amx.read(SEGMENTS), 'LCSQ')['settings']['time_segments']
    assert [s['time'] for s in segments] == [q(0.0, 'min'), q(2.0, 'min')]
    assert [[i['compound'] for i in s['monitored_ions']]
            for s in segments] == [['Caffeine'], ['Terphenyl']]
    assert [[i['mz'] for i in s['monitored_ions']]
            for s in segments] == [[q(195.0, 'm/z')], [q(230.0, 'm/z')]]
    assert all(len(s['scan_parameters']) == 1 for s in segments)


def test_a_fragmentor_ramp_is_stated_with_its_points():
    [segment] = _module(amx.read(POS_NEG), 'LCSQ')['settings']['time_segments']
    assert [(r['polarity'], r['fragmentor'])
            for r in segment['scan_parameters']] == [
        ('+', q(110.0, 'V')), ('-', 'Ramp(1)')]
    assert [(p['ramp'], p['mz']['value'], p['voltage']['value'])
            for p in segment['fragmentor_ramps']] == [
        ('Ramp(1)', 75.0, 90.0), ('Ramp(1)', 250.0, 100.0),
        ('Ramp(1)', 450.0, 110.0), ('Ramp(1)', 750.0, 120.0),
        ('Ramp(1)', 1000.0, 130.0)]


def test_a_scan_only_single_quad_monitors_no_ions():
    [segment] = _module(amx.read(SCAN), 'LCSQ')['settings']['time_segments']
    assert segment['scan_type'] == 'Scan'
    assert [(r['mz_low'], r['mz_high'])
            for r in segment['scan_parameters']] == [
        (q(100.0, 'm/z'), q(1000.0, 'm/z'))]
    assert 'monitored_ions' not in segment


def test_a_dad_signals_reference():
    dad = _module(amx.read(DAD_REF), 'Agilent1200erDadDriver')['settings']
    assert dad['signals'][0] == {
        'acquire': True, 'signal': 'Signal A',
        'wavelength': q(220.0, 'nm'), 'bandwidth': q(4.0, 'nm'),
        'use_reference': True, 'reference_wavelength': q(360.0, 'nm'),
        'reference_bandwidth': q(100.0, 'nm')}
    assert dad['signals'][1]['use_reference'] is False
    assert 'reference_wavelength' not in dad['signals'][1]


def test_a_module_whose_driver_part_records_no_model_has_no_driver(tmp_path):
    """A driver part with neither ModuleType nor <msModel> leaves its module
    without a driver: listed, with no settings, and the method reads."""
    source = zipfile.ZipFile(SCAN)
    out = tmp_path / "run.amx"
    with zipfile.ZipFile(out, "w") as package:
        for info in source.infolist():
            data = source.read(info)
            if info.filename == 'DeviceMethodSettings/LCSQ%25231':
                data = data.replace(b'<msModel>LC/MSD iQ</msModel>', b'')
            package.writestr(info, data)
    method = amx.read(str(out))
    assert method['module_settings'][0] == {
        'name': 'SQ Mass Spectrometer', 'model': 'LC/MSD iQ'}
    assert method['run_time'] == q(6.0, 'min')


# -- the method onto the run's MS data -----------------------------------

def _ms(path):
    datadir = rb.read(path, centroid=True, bin_width=1.0)
    [ms] = [f for f in datadir.datafiles if f.detector == 'MS']
    return ms.metadata


def test_a_sim_scan_runs_ms_file_states_its_method():
    ms = _ms(JADE)
    assert ms['scan_parameters'] == [{
        'time_segment': 1, 'time': 0.0, 'mz_low': 100.0, 'mz_high': 1000.0,
        'fragmentor': 110.0, 'polarity': '+', 'ionization_mode': 'ESI'}]
    assert ms['monitored_ions'] == [{
        'time_segment': 1, 'time': 0.0, 'mz': 295.0, 'fragmentor': 100.0,
        'compound': 'Caffeine', 'polarity': '+', 'ionization_mode': 'ESI'}]
    assert ms['ionization_mode'] == 'ESI' and ms['polarity'] == '+'
    # The scan row and the SIM ion are set to different fragmentors.
    assert 'fragmentor' not in ms
    assert 'method_disagrees' not in ms


def test_each_segments_ions_are_those_its_scans_recorded():
    ms = _ms(OCHRE)
    assert [(i['time_segment'], i['time'], i['mz'], i['compound'])
            for i in ms['monitored_ions']] == [
        (1, 0.0, 195.0, 'Caffeine'), (2, 2.0, 230.0, 'Terphenyl')]
    assert ms['fragmentor'] == 110.0
    assert 'method_disagrees' not in ms


def test_a_run_of_both_polarities_states_each_rows_own():
    ms = _ms(ROSE)
    assert [r['polarity'] for r in ms['scan_parameters']] == ['+', '-']
    assert ms['scan_parameters'][1]['fragmentor_ramp'][0] == {
        'mz': 75.0, 'voltage': 90.0}
    assert 'polarity' not in ms and 'fragmentor' not in ms
    assert 'monitored_ions' not in ms


def test_a_method_its_scans_dont_record_is_kept_apart(tmp_path):
    """The scans are the check: jade's run under ochre's method (other SIM
    ions, two segments) states none of it, and keeps it apart."""
    import shutil
    run = tmp_path / "jade.sirslt"
    shutil.copytree(JADE, run)
    (run / "example_MS_with_SIM.amx").unlink()
    shutil.copy(SEGMENTS, run / "jade.amx")
    ms = _ms(str(run))
    assert 'monitored_ions' not in ms and 'scan_parameters' not in ms
    rows = ms['method_disagrees']['time_segments']
    assert [r.get('compound') for r in rows if 'mz' in r] == [
        'Caffeine', 'Terphenyl']


def test_a_dad_only_run_states_its_reference_from_file_and_method():
    datadir = rb.read(CORAL)
    [a] = [f for f in datadir.datafiles if f.name == 'DAD1A.CH']
    assert a.metadata['reference_wavelength'] == 360.0
    assert a.metadata['reference_bandwidth'] == 100.0
    dad = _module(datadir.metadata, 'Agilent1200erDadDriver')['settings']
    assert dad['signals'][0]['reference_wavelength'] == q(360.0, 'nm')
