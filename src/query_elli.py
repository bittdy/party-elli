#!/usr/bin/env python3

import argparse
import tempfile

from elli import main, parse_acacia_spec
from helpers.main_helper import setup_logging, create_spec_converter_z3
from synthesis.smt_logic import UFLIA

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Save smt2 queries generated by elli')

    parser.add_argument('spec', metavar='spec', type=str,
                        help='the specification file (anzu, acacia+, or python format)')

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--moore', action='store_true', required=False,
                       help='assume a Moore model')
    group.add_argument('--mealy', action='store_false', required=False,
                       help='assume a Mealy model')

    parser.add_argument('--minsize', metavar='minsize', type=int, default=1, required=False,
                        help='start from size (default: %(default)i)')
    parser.add_argument('--maxsize', metavar='maxsize', type=int, default=4, required=False,
                        help='stop at this size (default: %(default)i)')

    parser.add_argument('-v', '--verbose', action='count', default=0)

    args = parser.parse_args()
    assert args.minsize <= args.maxsize

    logger = setup_logging(args.verbose)
    logger.info(args)

    with tempfile.NamedTemporaryFile(dir='./') as smt_file:
        smt_files_prefix = smt_file.name

    ltl2automaton_converter, solver_factory = create_spec_converter_z3(logger,
                                                                       UFLIA(None),
                                                                       False,
                                                                       True,
                                                                       smt_files_prefix,
                                                                       True)

    bounds = list(range(args.minsize, args.maxsize+1))

    solver = solver_factory.create()
    input_signals, output_signals, ltl = parse_acacia_spec(args.spec,
                                                           ltl2automaton_converter,
                                                           logger)
    is_realizable = main(input_signals,
                         output_signals,
                         ltl,
                         args.moore,
                         None,
                         bounds,
                         ltl2automaton_converter,
                         solver,
                         logger)
    solver.die()
    exit(0)