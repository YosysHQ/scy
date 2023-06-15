import argparse

def parser_func():
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
    parser.add_argument("--dumpcommon", action="store_true", dest="dump_common",
            help="prepare common input and exit")
    parser.add_argument("--setup", action="store_true", dest="setupmode",
            help="set up the working directory and exit")

    parser.add_argument('scyfile', metavar="<jobname>.scy",
            help=".scy file")
    return parser
