import json, uuid, os, datetime
from glob import glob
from types import SimpleNamespace

# file maps are implemented as dictionaries with the following format:
#   "rootFolderId" : "abcdef123"  # refers to the current root of the view,
#                                 # rather than the actual root of the tree
#   "baseAbsolutePath" : "path/a/b/"
#   "fileMap" : {
#      # common to both files and directories
#      "id" : "abcdef123"
#      "name" : "file_basename"
#      "modDate" : "2020-10-20T03:11:50.570Z"
#      "parentId" (present for all except the root) : "dasfdsafsd"
#
#      # if file
#      "size" : 1524 # in bytes
#     
#      # if directory
#      "isDir" : True
#      "childrenCount" : n                    # neither of these fields is
#      "childrenIds" : [ "abc", "def", ... ]  # populated until the directory
#                                             # is explored

# create a filemap by traversing the specified directory
# subdirectories will be noted but not explored
def initialize(base_absolute_path):
    # make sure we are initializing from a directory
    assert isinstance(base_absolute_path, str)
    assert os.path.isdir(base_absolute_path)
    if base_absolute_path[-1] != "/":
        base_absolute_path += "/"

    # create the root entry for the tree
    root_entry = _generate_entry(parent_id=None, absolute_path=base_absolute_path)
    root_folder_id = root_entry["id"]

    # create the file_map object
    file_map = {
        "rootFolderId"      : root_folder_id,
        "baseAbsolutePath"  : base_absolute_path,
        "fileMap"           : { root_folder_id : root_entry },
    }
    root_entry["name"] = base_absolute_path.split("/")[-2]

    # explore the base directory
    explore(file_map, root_entry)
    return file_map

# change the root of the tree to the specified folder
# and explore/refresh that folder
def set_root_folder(file_map, new_root_folder_id):
    fileMap = file_map["fileMap"]
    assert isinstance(new_root_folder_id, str)
    assert new_root_folder_id in fileMap
    file_map["rootFolderId"] = new_root_folder_id
    new_root_entry = fileMap[new_root_folder_id]
    explore(file_map, new_root_entry)

# explore the specified path
def explore(file_map, entry):
    # sanity checks
    assert isinstance(file_map, dict)
    assert "baseAbsolutePath" in file_map
    assert isinstance(entry, dict)
    assert "isDir" in entry and entry["isDir"] is True
    fileMap = file_map["fileMap"]

    # parent id of the new entries 
    parent_id = entry["id"]

    # recursively remove any existing children
    def prune(entry):
        id = entry["id"]
        if "childrenIds" in entry:
            for id in entry["childrenIds"]:
                if id in fileMap:
                    child_entry = fileMap[id]
                    prune(child_entry)
                    del fileMap[id]
                else:
                    print(f"Warning: expected key {id} when exploring directory {entry['name']}!")
    prune(entry)

    # glob this directory
    absolute_path = _get_absolute_path(file_map, entry["id"])  # abs path of the parent
    new_entries = [ _generate_entry(parent_id, f) for f in sorted(glob(f"{absolute_path}/*")) ]
    for e in new_entries:
        id = e["id"]
        fileMap[id] = e
    entry["childrenIds"] = [ e["id"] for e in new_entries ]
    entry["childrenCount"] = len(new_entries)

# get the absolute path for the specified id
def _get_absolute_path(file_map, id):
    fileMap = file_map["fileMap"]
    entry = fileMap[id]

    # store the path in here
    path = []

    # search one level up
    def search(entry):
        # this will cause termination at the root of the tree
        if "parentId" in entry:
            # add the current name to the path
            entry_name = entry["name"]
            if entry_name[-1] != "/":
                entry_name += "/"
            path.append(entry_name)

            # get the parent node
            parent_id = entry["parentId"]
            parent_entry = fileMap[parent_id]

            # ensure that the parent node is a directory
            assert "isDir" in parent_entry
            assert parent_entry["isDir"] is True

            # recurse upwards one level
            entry = fileMap[parent_id]
            search(parent_entry)

    # run the search and reverse to get the result
    search(entry)
    path.append(file_map["baseAbsolutePath"])
    path = path[::-1]
    absolute_path = ''.join(path)
    #print(absolute_path)
    return absolute_path

# generate a dictionary key/value pair for a given absolute path
# no checks are made on absolute_path as this method is not meant
# to be called externally
def _generate_entry(parent_id, absolute_path):
    # fields common to files and directories
    epoch_time = os.path.getmtime(absolute_path)
    entry = {
        "id"      : str(uuid.uuid4()),
        "name"    : absolute_path.split("/")[-1],
        "modDate" : str(datetime.datetime.fromtimestamp(epoch_time)),
    }
    if parent_id is not None:
        entry["parentId"] = parent_id

    # determine if this is a directory
    assert isinstance(absolute_path, str)
    assert os.path.exists(absolute_path)
    is_directory = os.path.isdir(absolute_path)

    if is_directory:
        entry["isDir"] = True
        entry["childrenIds"] = []
        entry["childrenCount"] = 0
    else:
        entry["size"] = os.path.getsize(absolute_path)

    # return result
    return entry

# find ids corresponding to the given absolute path
# or return an empty list if nothing found
def _search(file_map, absolute_path):
    assert isinstance(file_map, dict)
    assert isinstance(absolute_path, str)
    if absolute_path[-1] != "/":
        absolute_path += "/"
    name = absolute_path.split("/")[-2]
    results = []
    for id,entry in file_map["fileMap"].items():
        if entry["name"] == name:
            this_absolute_path = _get_absolute_path(file_map, id)
            if this_absolute_path == absolute_path:
                results.append(id)
    return results

# check every entry points to child ids that are in the filemap
def _check_children(file_map):
    fileMap = file_map["fileMap"]
    for id,entry in fileMap.items():
        if "childrenIds" in entry:
            childrenIds = entry["childrenIds"]
            for id in childrenIds:
                assert id in fileMap, f"missing child for entry {entry['name']}"

def _print_function(o):
    o_dict = { k : v for k,v in o.__dict__.items() }
    return o_dict

# pretty print
def pprint(file_map):
    print(json.dumps(file_map, default=_print_function, indent=2))

# dump minified json
def dump(file_map):
    return json.dumps(file_map, default=_print_function, indent=None, separators=(',',':'))

# for testing
if __name__ == "__main__":
    file_map = initialize("/Users/ekwan/research/rainbow/data")
    root_id = file_map["rootFolderId"]
    fileMap = file_map["fileMap"]
    pprint(fileMap)
    round2_id = None
    for id,entry in fileMap.items():
        if entry["name"] == "round2":
            round2_id = id
            break
    print(len(fileMap))
    explore(file_map, fileMap[round2_id])
    a2_id = None
    for id,entry in fileMap.items():
        if entry["name"] == "A2Rd2_01":
            a2_id = id
            break
    explore(file_map, fileMap[a2_id])
    print(len(fileMap))
    explore(file_map, fileMap[root_id])
    print(len(fileMap))
    pprint(fileMap)
