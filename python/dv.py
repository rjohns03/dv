#!/apps/base/python3/bin/python

import os
import re
import sys
import json
import time
import math
import gzip
import shutil
import string
import random
import hashlib
import argparse
import multiprocessing
from http.server import SimpleHTTPRequestHandler, HTTPServer


DV_LOCATION = os.path.dirname(os.path.realpath(__file__))
WWW_LOCATION = os.path.join(os.path.dirname(DV_LOCATION), "www")


class Server(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.gzip_headers()
        SimpleHTTPRequestHandler.end_headers(self)

    def gzip_headers(self):
        if self.path == "/scan.json":
            self.send_header("Content-Encoding", "gzip")

    def log_message(self, format_string, *log_args):
        return


class DotDict(dict):
    """DotDict wraps the default dictionary to provide dot operator access
    (dict.foo instead of dict["foo"])
    """
    def __getattr__(self, attr):
        return self.get(attr)
    __setattr__ = dict.__setitem__


def parseArgs():
    """parseArgs will parse sys.argv to create a mapping of args that can be accessed via the dot operator
    """

    HELP = DotDict({
        "processes": "Number of processes to scan with (defaults to 5)",
        "depth": "Depth of directory tree to show in browser (defaults to 10)",
        "unique": "If passed, the 'unique' flag generates a new plot with a unique URL instead of overwriting the previous scan",
        "modtime": "If passed, the 'modtime' flag adds the most recent modification time of any file in each directory to the generated plot",
        "fade": "If passed, the 'fade' flag will make directories in the generated plot appear more gray if their files haven't been touched for a long time",
        "save": "A directory containing the generated plot and web page will be placed on disk at the specified location, after the scan finishes",
        "save_and_host": "The same as -s, but after scanning, dv will start a server to serve the newly generated plot",
        "port": "If using --save-and-host, specifies the port of the dv webserver. Defaults to 8000"
    })

    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=str, help="Directory for dv to scan")
    parser.add_argument("--processes", "-p", nargs="?", type=int, default=5, help=HELP.processes)
    parser.add_argument("--depth", "-d", nargs="?", type=int, default=10, help=HELP.depth)
    parser.add_argument("-u", "--unique", action="store_true", help=HELP.unique)
    parser.add_argument("-m", "--modtime", action="store_true", help=HELP.modtime)
    parser.add_argument("-f", "--fade", action="store_true", help=HELP.fade)
    parser.add_argument("-s", "--save", help=HELP.save)
    parser.add_argument("-sh", "--save-and-host", help=HELP.save_and_host)
    parser.add_argument("--port", default=8000, type=int, help=HELP.port)
    parser.add_argument("--multiprocessing-fork", help=argparse.SUPPRESS)

    args = parser.parse_args()
    args.root = args.directory

    if args.save_and_host:
        args.save = args.save_and_host
    if args.save:
        args.save = os.path.realpath(args.save)

    args.drive_letter = ""
    if re.match(r"[A-Z]:\\", args.root):
        # On windows, save drive letter
        split_root = args.root.split("\\", 1)
        args.drive_letter = split_root[0]
        args.root = "\\" + split_root[1]

    if args.root == os.path.sep:
        args.root = "{0}.{0}".format(os.path.sep)
    else:
        args.root = os.path.abspath(args.root)

    if args.root.endswith(os.path.sep):
        args.root = args.root[:-1]

    if not os.path.exists(args.root):
        sys.exit("{} does not exist".format(args.root))

    if args.fade:
        args.modtime = True

    return args


def getRandomToken():
    """getRandomToken generates a cryptographically secure 25 character token, where each character
    has 62 possible values, providing a total of 62^25 possible output values
    """
    LENGTH = 10
    ID = ""
    rand_gen = random.SystemRandom()
    for _ in range(LENGTH):
        new_char = rand_gen.choice(string.ascii_letters + string.digits)
        ID += new_char
    return ID


def getRootBasedToken():
    md5 = hashlib.md5()
    md5.update(args.root.encode("utf-8"))
    return md5.hexdigest()


def getToken():
    raise NotImplementedError("getToken should be overriden by a token generation method")


def scanDir(in_queue, out_queue, drive_letter):
    while 1:
        total_bytes = 0
        total_files = 0
        newest_time = 0
        try:
            path = in_queue.get(False)
        except Exception:
            time.sleep(0.05)
            continue
        if path == "__DONE__":
            out_queue.put("__DONE__")
            return

        try:
            item_gen = os.scandir(drive_letter + path)
        except (FileNotFoundError, PermissionError):
            continue

        for item in item_gen:
            try:
                if item.is_dir(follow_symlinks=False):
                    continue
                stat_result = item.stat(follow_symlinks=False)
                item_size = stat_result.st_size
                if stat_result.st_mtime > newest_time:
                    newest_time = int(stat_result.st_mtime)

                total_bytes += item_size
                total_files += 1
            except (FileNotFoundError, PermissionError):
                pass

        if drive_letter:
            path = path.replace(drive_letter, "", 1)
        out_queue.put([path, total_bytes, total_files, newest_time])


def scaffoldDir(path, scaffold, depth=1):
    if args.drive_letter:
        path = path.replace(args.drive_letter, "", 1)

    if depth > collection_vars["tree_depth"]:
        collection_vars["tree_depth"] = depth

    base_path = os.path.basename(path)

    new_node = {"name": base_path, "size": 0, "count": 0, "children": {}}
    if(args.modtime):
        new_node["mtime"] = 0

    scaffold["children"][base_path] = new_node

    try:
        item_gen = os.scandir(args.drive_letter + path)
    except Exception as e:
        return

    work_queue.put(path)

    for item in item_gen:
        try:
            if item.is_dir(follow_symlinks=False):
                scaffoldDir(item.path, new_node, depth=depth + 1)
        except (FileNotFoundError, PermissionError):
            pass


def getRootDir(root):
    if root.count(os.path.sep) < 2:
        return root
    else:
        return os.path.dirname(root)


def getRootCount(root):
    part_count = root.count(os.path.sep)
    root_segment = os.path.sep + "root"
    if part_count >= 2:
        return root_segment
    else:
        return root_segment + args.root


def joinNode(node):
    node[0] = root_append + node[0].replace(root_dir, "", 1)
    path_parts = node[0].split(os.path.sep)[1:]
    current = scaffold
    for depth, part in enumerate(path_parts):
        if depth + 1 > args.depth:
            break

        current = current[part]
        current["size"] += node[1]
        current["count"] += node[2]
        if args.modtime and node[3] > current["mtime"]:
            if node[3] > collection_vars["newest_dir"]:
                collection_vars["newest_dir"] = node[3]
            if node[3] < collection_vars["oldest_dir"]:
                collection_vars["oldest_dir"] = node[3]
            current["mtime"] = node[3]

        current = current["children"]


def writeFile(run_id, data, file_root="/data/tmp/dv"):
    if args.save:
        file_name = "scan.json"
    else:
        file_name = "dv_{}.json".format(run_id)

    write_path = os.path.join(file_root, file_name)

    fi = gzip.open(write_path, "wb")
    fi.write(bytes(data, encoding="utf-8"))
    fi.close()


def writeOutDir(run_id, data):
    dir_path = os.path.join(args.save, "dv_" + run_id)

    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)

    shutil.copytree(WWW_LOCATION, dir_path)

    writeFile(run_id, data, dir_path)


def joinNodes():
    done_procs = 0
    while 1:
        try:
            next_node = done_queue.get(False)
        except Exception:
            continue
        if next_node == "__DONE__":
            done_procs += 1
            if done_procs == args.processes:
                break
            continue
        joinNode(next_node)

    for proc in processes:
        proc.join(timeout=0.5)


def setScaffoldMetadata():
    # Embed custom variables into JSON to save time
    scaffold["tree_depth"] = collection_vars["tree_depth"]
    scaffold["max_depth"] = args.depth
    scaffold["scanned_dir"] = args.root
    scaffold["scan_time"] = int(time.time())
    scaffold["mtime_on"] = args.modtime
    scaffold["path_sep"] = os.path.sep
    scaffold["drive_letter"] = args.drive_letter

    scaffold["fade_on"] = args.fade
    scaffold["oldest_dir"] = collection_vars["oldest_dir"]
    scaffold["newest_dir"] = collection_vars["newest_dir"]

    scaffold["fs_total_bytes"] = shutil.disk_usage(args.drive_letter + args.root).total

    return scaffold


def pruneData():
    total_size = scaffold["root"]["size"]
    total_count = scaffold["root"]["count"]

    pruneNode(scaffold["root"], total_size, total_count)


def pruneNode(node, total_size, total_count):
    rm_nodes = []

    for key, child in node["children"].items():
        size_thickness = math.pi * 2 * (node["size"] / total_size)
        count_thickness = math.pi * 2 * (node["count"] / total_count)
        if size_thickness < 0.005 and count_thickness < 0.005:
            rm_nodes.append(key)
        else:
            pruneNode(child, total_size, total_count)

    for rm_node in rm_nodes:
        del node["children"][rm_node]


if __name__ == "__main__":
    multiprocessing.freeze_support()
    args = parseArgs()

    if args.save and not os.path.exists(WWW_LOCATION):
        sys.exit("Web dir '{}' not found".format(WWW_LOCATION))

    if args.unique:
        getToken = getRandomToken
    else:
        getToken = getRootBasedToken

    manager = multiprocessing.Manager()
    work_queue = manager.Queue()
    done_queue = manager.Queue()

    root_dir = getRootDir(args.root)
    root_append = getRootCount(args.root)

    processes = []
    for proc in range(args.processes):
        new_proc = multiprocessing.Process(target=scanDir, args=(work_queue, done_queue, args.drive_letter, ))
        processes.append(new_proc)
        new_proc.daemon = True
        new_proc.start()

    collection_vars = {"tree_depth": 0, "oldest_dir": time.time(), "newest_dir": 0}
    scaffold = {"root": {"name": "root", "size": 0, "mtime": 0, "count": 0, "children": {}}}
    scaffoldDir(args.drive_letter + args.root, scaffold["root"])

    for proc in range(args.processes):
        work_queue.put("__DONE__")

    joinNodes()
    setScaffoldMetadata()

    pruneData()

    file_json = json.dumps(scaffold)
    token = getToken()

    if args.save:
        writeOutDir(token, file_json)
    else:
        writeFile(token, file_json)

    print("Your plot can be found at:")
    if args.save_and_host:
        dir_path = os.path.join(args.save, "dv_" + token)
        print("[Ctrl+C to stop]")
        print("http://localhost:{}?id=local".format(args.port))
        os.chdir(dir_path)
        server = HTTPServer(("localhost", args.port), Server)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            sys.exit("\nStopped")
    elif args.save:
        dir_path = os.path.join(args.save, "dv_" + token)
        print(dir_path)
    else:
        print("https://engineering.arm.gov/dv?id=%s" % token)
