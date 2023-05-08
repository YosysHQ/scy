import os, sys, re
import argparse
import subprocess
from scy_task_tree import TaskTree

parser = argparse.ArgumentParser(prog="scy")

# input arguments
# mostly just a quick hack while waiting for common frontend
parser.add_argument("-d", metavar="<dirname>", dest="workdir",
        help="set workdir name. default: <jobname>")
parser.add_argument("-f", action="store_true", dest="force",
        help="remove workdir if it already exists")

parser.add_argument("-j", metavar="<N>", type=int, dest="jobcount",
        help="maximum number of processes to run in parallel")

parser.add_argument("--dumptree", action="store_true", dest="dump_tree",
        help="print the task tree and exit")
parser.add_argument("--setup", action="store_true", dest="setupmode",
        help="set up the working directory and exit")

parser.add_argument('scyfile', metavar="<jobname>.scy",
        help=".scy file")

args = parser.parse_args()
scyfile = args.scyfile

# parse scy file

with open(scyfile, 'r') as f:
    scydata = f.read()

regex = r"(?:^|\n)\[(?P<name>.*)\]\n(?P<body>(?:\n?.*)*?(?=\n\[|$))"
sections = re.finditer(regex, scydata)
sectDict = { m['name']:m['body'].split('\n') for m in sections }

start_index = scydata.split('\n').index("[sequence]") + 2
task_tree = TaskTree.from_sequence(sectDict["sequence"], L0 = start_index)

if args.dump_tree:
    print(task_tree)
    sys.exit(0)

# generate sby files

# generate makefile

if args.setupmode:
    sys.exit(0)

# run makefile
retcode = 0

# parse sby runs

# output stats

sys.exit(retcode)
