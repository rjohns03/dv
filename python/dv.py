#!/apps/base/python3/bin/python

import os
import sys
import json
import time
import gzip
import shutil
import string
import random
import hashlib
import argparse
from http.server import *
from multiprocessing import Manager, Process


class Server(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.gzip_headers()
        SimpleHTTPRequestHandler.end_headers(self)

    def gzip_headers(self):
        if self.path == "/scan.json":
            self.send_header("Content-Encoding", "gzip")

    def log_message(self, format, *args):
        return


def parseArgs():
    """parseArgs will parse sys.argv to create a mapping of args that can be accessed via the dot operator
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=str, help="Directory for dv to scan")
    parser.add_argument("--processes", "-p", nargs="?", type=int, default=5, help="Number of processes to scan with (defaults to 5)")
    parser.add_argument("--depth", "-d", nargs="?", type=int, default=10, help="Depth of directory tree to show in browser (defaults to 10)")
    parser.add_argument("-u", "--unique", action="store_true", help="If passed, the 'unique' flag generates a new plot with a unique URL instead of overwriting the previous scan")
    parser.add_argument("-m", "--modtime", action="store_true", help="If passed, the 'modtime' flag adds the most recent modification time of any file in each directory to the generated plot")
    parser.add_argument("-f", "--fade", action="store_true", help="If passed, the 'fade' flag will make directories in the generated plot appear more opaque if their files haven't been touched for a long time")
    parser.add_argument("-o", "--output", help="A directory containing the generated plot and web page will be placed on disk at the specified location, after the scan finishes, a local HTTP server will start and serve the plot")

    args = parser.parse_args()
    args.root = args.directory

    if args.root.endswith("/"):
        args.root = args.root[:-1]
    if not os.path.exists(args.root):
        sys.exit("{} does not exist".format(args.root))

    if args.fade:
        args.modtime = True

    return args


def parseConfig():
    """Parse the file config.json found in the same directory
    """
    config_name = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.json")

    try:
        config_contents = open(config_name).read()
    except Exception:
        sys.exit("Couldn't find config file")

    try:
        config_json = json.loads(config_contents)
    except Exception:
        sys.exit("Malformed JSON in config file")

    return config_json


def getRandomToken():
    """getRandomToken generates a cryptographically secure 25 character token, where each character
    has 62 possible values, providing a total of 62^25 possible output values
    """
    LENGTH = 10
    ID = ""
    rand_gen = random.SystemRandom()
    for x in range(LENGTH):
        new_char = rand_gen.choice(string.ascii_letters + string.digits)
        ID += new_char
    return ID


def getRootBasedToken():
    md5 = hashlib.md5()
    md5.update(args.root.encode("utf-8"))
    return md5.hexdigest()


def getToken():
    raise NotImplementedError("getToken should be overriden by a token generation method")


def scanDir(in_queue, out_queue):
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
            item_gen = os.scandir(path)
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

        out_queue.put([path, total_bytes, total_files, newest_time])


def scaffoldDir(path, scaffold, depth=1):
    if depth > collection_vars["tree_depth"]:
        collection_vars["tree_depth"] = depth

    base_path = os.path.basename(path)

    new_node = {"name": base_path, "size": 0, "count": 0, "children": {}}
    if(args.modtime):
        new_node["mtime"] = 0

    scaffold["children"][base_path] = new_node

    try:
        item_gen = os.scandir(path)
    except Exception:
        return
    work_queue.put(path)

    for item in item_gen:
        try:
            if item.is_dir(follow_symlinks=False):
                scaffoldDir(item.path, new_node, depth=depth + 1)
        except (FileNotFoundError, PermissionError):
            pass


def getRootDir(root):
    if root.count("/") < 2:
        return root
    else:
        return os.path.dirname(root)


def getRootCount(root):
    part_count = root.count("/")
    if part_count >= 2:
        return "/root"
    else:
        return "/root" + args.root


def joinNode(node):
    node[0] = root_append + node[0].replace(root_dir, "", 1)
    path_parts = node[0].split("/")[1:]
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
    if args.output:
        file_name = "scan.json"
    else:
        file_name = "dv_{}.json".format(run_id)

    write_path = os.path.join(file_root, file_name)

    fi = gzip.open(write_path, "wb")
    fi.write(bytes(data, encoding="utf-8"))
    fi.close()


def writeOutDir(run_id, data):
    dir_path = os.path.join(args.output, "dv_" + run_id)

    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)

    shutil.copytree(config["web_dir"], dir_path)

    writeFile(run_id, data, dir_path)


if __name__ == "__main__":
    args = parseArgs()
    config = parseConfig()

    if args.unique:
        getToken = getRandomToken
    else:
        getToken = getRootBasedToken

    manager = Manager()
    work_queue = manager.Queue()
    done_queue = manager.Queue()

    root_dir = getRootDir(args.root)
    root_append = getRootCount(args.root)

    processes = []
    for proc in range(args.processes):
        new_proc = Process(target=scanDir, args=(work_queue, done_queue, ))
        processes.append(new_proc)
        new_proc.start()

    collection_vars = {"tree_depth": 0, "oldest_dir": time.time(), "newest_dir": 0}
    scaffold = {"root": {"name": "root", "size": 0, "mtime": 0, "count": 0, "children": {}}}
    scaffoldDir(args.root, scaffold["root"])

    for proc in range(args.processes):
        work_queue.put("__DONE__")

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

    # Embed custom variables into JSON to save time
    scaffold["tree_depth"] = collection_vars["tree_depth"]
    scaffold["max_depth"] = args.depth
    scaffold["scanned_dir"] = args.root
    scaffold["scan_time"] = int(time.time())
    scaffold["mtime_on"] = args.modtime

    scaffold["fade_on"] = args.fade
    scaffold["oldest_dir"] = collection_vars["oldest_dir"]
    scaffold["newest_dir"] = collection_vars["newest_dir"]

    fs_stat = os.statvfs(args.root)
    fs_bytes = fs_stat.f_bsize * fs_stat.f_blocks
    scaffold["fs_total_bytes"] = fs_bytes

    file_json = json.dumps(scaffold)
    token = getToken()

    if args.output:
        writeOutDir(token, file_json)
    else:
        writeFile(token, file_json)

    print("Your plot can be found at:")
    if args.output:
        dir_path = os.path.join(args.output, "dv_" + token)
        print("localhost:8000?id=local")
        os.chdir(dir_path)
        server = HTTPServer(("localhost", 8000), Server)
        server.serve_forever()
    else:
        print("https://engineering.arm.gov/dv?id=%s" % token)
