""" 
This script is used for benchmarking.

"""

import os
import rainbow as rb
from rainbow import agilent, waters


time_benchmark = False
use_mp = False
time_by_line = False
method_to_time = None

memory_benchmark = False

DATASET = "MY_DATASET"
dirpaths = [os.path.join(DATASET, name) for name in os.listdir(DATASET)
            if name != ".DS_Store"]

# You can test a single data folder as follows:
# dirpaths = ["MY_DATASET/test.raw"]

def display_top(snapshot, key_type='lineno', limit=3):
    """
    Utility method for displaying memory usage by line. 
    If more detailed information is needed, use the `memory_profiler` library.

    """
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

def main():
    """
    Run tests in here. 
    
    """
    if use_mp:
        import multiprocessing as mp
        pool = mp.Pool()
        datadirs = pool.map(rb.read, dirpaths)
        pool.close()
        pool.join()
        return datadirs

    datadirs = []
    for folder in dirpaths:
        datadirs.append(rb.read(folder))
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