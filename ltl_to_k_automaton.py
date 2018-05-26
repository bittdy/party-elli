#!/usr/bin/env python3

import argparse

from LTL_to_atm import translator_via_ltl3ba, translator_via_spot
from automata.atm_to_spot import convert_to_spot_automaton
from automata.k_reduction import k_reduce
from helpers.main_helper import setup_logging
from interfaces.LTL_to_automaton import LTLToAutomaton
from parsing.acacia_parser_helper import parse_acacia_and_build_expr
from parsing.tlsf_parser import convert_tlsf_or_acacia_to_acacia


def main():
    parser = argparse.ArgumentParser(description='Translate LTL spec (TLSF or Acacia format) into k-automaton (HOA format)',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('spec', metavar='spec', type=str,
                        help='input spec (Acacia or TLSF format)')

    parser.add_argument('--k', '-k', default=8, required=False, type=int,
                        help='max number of visits to a bad state (within one SCC)')

    gr = parser.add_mutually_exclusive_group()
    gr.add_argument('--spot', action='store_true', default=True,
                    dest='spot',
                    help='use SPOT for translating LTL->BA')
    gr.add_argument('--ltl3ba', action='store_false', default=False,
                    dest='spot',
                    help='use LTL3BA for translating LTL->BA')

    parser.add_argument('--noopt', action='store_true', default=False,
                        dest='noopt',
                        help='Do not strengthen the specification (using the separation into safety-liveness)')

    parser.add_argument('--hoa', required=False, type=str,
                        help='output HOA file')

    parser.add_argument('-v', '--verbose', action='count', default=0)

    args = parser.parse_args()
    setup_logging(args.verbose)
    print(args)

    ltl_to_automaton = (translator_via_ltl3ba.LTLToAtmViaLTL3BA,
                        translator_via_spot.LTLToAtmViaSpot)[args.spot]()  # type: LTLToAutomaton

    ltl_text, part_text, _ = convert_tlsf_or_acacia_to_acacia(args.spec,
                                                              False  # does not matter
                                                              )

    spec = parse_acacia_and_build_expr(ltl_text, part_text,
                                       ltl_to_automaton,
                                       0 if args.noopt else 2)

    ucw_automaton = ltl_to_automaton.convert(spec.formula)
    k_automaton = k_reduce(ucw_automaton, args.k)
    spot_k_automaton = convert_to_spot_automaton(k_automaton)
    spot_k_automaton = spot_k_automaton.postprocess('SBAcc')  # this postprocessing kills state names
    spot_k_automaton.prop_terminal(True)

    if args.out:
        with open(args.out, 'w') as f:
            f.write(spot_k_automaton.to_str('hoa'))
    else:
        print(spot_k_automaton.to_str('dot'))


if __name__ == '__main__':
    main()