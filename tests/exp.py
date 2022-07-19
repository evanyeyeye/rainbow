""" 
This script is used for benchmarking and exploratory testing.

"""

import os
import rainbow as rb


time_benchmark = True
use_mp = False 
time_by_line = False
method_to_time = None

memory_benchmark = False

# dataset_dir = "../../../Downloads/datasets/agilent/FID/"
# data_folders = [dataset_dir + dir for dir in os.listdir(dataset_dir) if dir != ".DS_Store"]

data_folders = ["inputs/violet.raw"]

# data_folders = ["../../../Downloads/agilent/gcms/cedrol_mix_01.D"]
# data_folders = ["../../../Downloads/agilent/fid/caye_nmr_test_mix .D"]
# data_folders = ["../../../Downloads/agilent/hdr/HDR_data_example.D"]
# data_folders = ["../../../Downloads/agilent/partial/Ajit-Partial.D"]
# data_folders = ["../../../Downloads/agilent/partial/Ajit-Finished.D"]
# data_folders = ["../../../Downloads/agilent/lcms/100518-RM_HPLC-01970.D"]
# data_folders = ["../../../Downloads/agilent/hrms/5057649-0007_160622_3035.d"]
# data_folders = ["../../../Downloads/agilent/fid/emma_26Oct2020/Emma-5001483-0557.D"]

# data_folders = ["../../../Downloads/waters/cad/5042373-0175-35C_evap-Noscapine3-35C_evap-1-m09.raw"]
# data_folders = ["../../../Downloads/waters/elsd/2021-07-28-PROTEIN-261.raw"]
# data_folders = ["../../../Downloads/waters/sfcms/ok.raw"]
# data_folders = ["../../../Downloads/waters/elsd/2021-07-28-PROTEIN-261.raw"]
# data_folders = ["../../../Downloads/waters/uv/grahatho-5023368-0470-IPA-2.Raw"]
# data_folders = ["../../../Downloads/waters/uv/bharatin-IPA-5019324-0577-4.Raw"]
# data_folders = ["../../../Downloads/waters/lcms/Bita Parvizian1-1.raw"]
# data_folders = ["../../../Downloads/waters/lcms/blank1203_01d.raw"]
# data_folders = ["../../../Downloads/waters/lcms/meohflushcol10_1.raw"]
# data_folders = ["../../../Downloads/waters/elsd/2021-07-28-PROTEIN-296.raw"]
# data_folders = ["../../../Downloads/waters/lcms/meohflushcol10_1.raw", "../../../Downloads/waters/elsd/2021-07-28-PROTEIN-296.raw"]


def display_top(snapshot, key_type='lineno', limit=3):
    snapshot = snapshot.filter_traces((
        tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
        tracemalloc.Filter(False, "<unknown>"),
    ))
    top_stats = snapshot.statistics(key_type)

    print(f"Top {limit} lines")
    for index, stat in enumerate(top_stats[:limit], 1):
        frame = stat.traceback[0]
        filename = os.sep.join(frame.filename.split(os.sep)[-2:])
        print(f"#{index}: {filename}:{frame.lineno}: \
                          {stat.size / (1024 * 1024) :.3f} MiB")
        line = linecache.getline(frame.filename, frame.lineno).strip()
        if line:
            print(f'    {line}')

    other = top_stats[limit:]
    if other:
        size = sum(stat.size for stat in other)
        print(f"{len(other)} other: {size / (1024 * 1024) :.3f} MiB")
    total = sum(stat.size for stat in top_stats)
    print(f"Total allocated size: {total / (1024 * 1024) :.3f} MiB")

def debug_size(d):
    print("=" * len(d.name))
    print(d.name)
    print("=" * len(d.name))
    for name, f in d.by_name.items():
        print(f"{name}: {f.xlabels.size} {f.ylabels.size} {f.data.shape}")
    print()

def main():

    if use_mp:
        import multiprocessing as mp
        pool = mp.Pool()
        datadirs = pool.map(rb.read, data_folders)
        pool.close()
        pool.join()
        return datadirs

    datadirs = []
    # # print(len(data_folders))
    # for folder in data_folders:
    #     datadirs.append(rb.read(folder))
    #     if not datadirs[-1]:
    #         raise Exception("YOOO")
    #     if len(datadirs[-1].datafiles) == 0:
    #         print(datadirs[-1])
    #         raise Exception("BOOO")
    #     print(datadirs[-1])
    
    # print(datadirs[-1].get_info())
    # for i in datadirs[-1].analog:
    #     print(i.metadata)
    # # datadirs[-1].list_analog()
    # debug_size(datadirs[-1])
    
    return datadirs


if __name__ == '__main__':

    if time_benchmark:
        if time_by_line: 
            from line_profiler import LineProfiler
            lp = LineProfiler()
            lp.add_function(method_to_time)
            lp.enable_by_count()
        else:
            import cProfile
            import pstats
            profiler = cProfile.Profile()
            profiler.enable()
    if memory_benchmark:
        import tracemalloc 
        import linecache 
        import psutil 
        tracemalloc.start() 

    mem = main() 

    if time_benchmark:
        if time_by_line: 
            lp.print_stats(output_unit=1e-3)
        else:
            p = pstats.Stats(profiler).strip_dirs().sort_stats('tottime')
            p.print_stats(10)
    if memory_benchmark:
        display_top(tracemalloc.take_snapshot(), limit=5)
        ram_used = psutil.Process().memory_info().rss / (1024 * 1024)
        print(f"RAM Usage: {ram_used :.3f} MiB")