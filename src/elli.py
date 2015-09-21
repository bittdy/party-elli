#!/usr/bin/env python3
import argparse
from functools import lru_cache
import tempfile

from helpers import automaton2dot
from helpers.automata_classifier import is_safety_automaton
from helpers.gr1helpers import convert_into_gr1_formula
from helpers.main_helper import setup_logging, create_spec_converter_z3, remove_files_prefixed
from helpers.python_ext import readfile
from interfaces.expr import Expr, BinOp, UnaryOp, and_expressions
from module_generation.dot import lts_to_dot
from parsing.acacia_parser_desc import acacia_parser
from parsing.python_spec_parser import parse_python_spec
from parsing.visitor import Visitor
from synthesis import original_model_searcher, model_searcher
from synthesis.funcs_args_types_names import ARG_MODEL_STATE
from synthesis.smt_encoder import SMTEncoder
from synthesis.smt_logic import UFLIA
from automata_translations.ltl2automaton import LTL3BA


def write_out(model, is_moore, file_type, file_name):
    with open(file_name + '.' + file_type, 'w') as out:
        out.write(model)

        logger.info('{model_type} model is written to {file}'.format(
            model_type=['Mealy', 'Moore'][is_moore],
            file=out.name))


@lru_cache()
def is_safety_ltl(expr:Expr, ltl2automaton_converter) -> bool:
    automaton = ltl2automaton_converter.convert(-expr)  # !(safety ltl) has safety automaton
    res = is_safety_automaton(automaton)
    return res


@lru_cache()
def is_boolean_ltl(expr:Expr, ltl2automaton_converter) -> bool:
    class TemporalOperatorFoundException(Exception):
        pass

    class TemporalOperatorsFinder(Visitor):
        def visit_binary_op(self, binary_op:BinOp):
            if binary_op.name in ['W', 'U']:  # TODO: get rid of magic string constants
                raise TemporalOperatorFoundException()
            return super().visit_binary_op(binary_op)

        def visit_unary_op(self, unary_op:UnaryOp):
            if unary_op in ['G', 'F']:
                raise TemporalOperatorFoundException()
            return super().visit_unary_op(unary_op)
    try:
        TemporalOperatorsFinder().dispatch(expr)
        return True
    except TemporalOperatorFoundException:
        return False


def _gr1_classify(formulas):
    formulas = set(formulas)
    init = set(filter(is_boolean_ltl, formulas))
    safety = set(filter(is_safety_ltl, formulas - init))
    liveness = formulas - safety - init
    return init, safety, liveness


def _get_acacia_spec(ltl_text:str, part_text:str) -> (list, list, Expr):
    input_signals, output_signals, data_by_name = acacia_parser.parse(ltl_text, part_text, logger)

    if data_by_name is None:
        return None, None, None

    ltl_properties = []
    for (unit_name, unit_data) in data_by_name.items():
        assumptions = unit_data[0]
        guarantees = unit_data[1]
        a_init, a_safety, a_liveness = (and_expressions(p) for p in _gr1_classify(assumptions))
        g_init, g_safety, g_liveness = (and_expressions(p) for p in _gr1_classify(guarantees))
        ltl_property = convert_into_gr1_formula(a_init, g_init,
                                                a_safety, g_safety,
                                                a_liveness, g_liveness)
        ltl_properties.append(ltl_property)

    return input_signals, output_signals, and_expressions(ltl_properties)


def parse_anzu_spec(spec_file_name:str):
    raise NotImplemented('the code is not yet taken from the original parameterized tool')


def parse_acacia_spec(spec_file_name:str):
    """ :return: (inputs_signals, output_signals, expr) """

    assert spec_file_name.endswith('.ltl'), spec_file_name
    ltl_file_str = readfile(spec_file_name)
    part_file_str = readfile(spec_file_name.replace('.ltl', '.part'))
    return _get_acacia_spec(ltl_file_str, part_file_str)


def _get_tau_desc(inputs):
    arg_types_dict = dict()
    arg_types_dict[ARG_MODEL_STATE] = TYPE_MODEL_STATE

    for s in inputs:
        arg_types_dict[smt_arg_name_signal(s)] = 'Bool'

    tau_desc = FuncDescription(FUNC_MODEL_TRANS, arg_types_dict, TYPE_MODEL_STATE, None)
    return tau_desc


def _get_output_desc(output:Signal, is_mealy, inputs):
    arg_types_dict = dict()
    arg_types_dict[ARG_MODEL_STATE] = TYPE_MODEL_STATE

    if is_mealy:
        for s in inputs:
            arg_types_dict[smt_arg_name_signal(s)] = 'Bool'

    return FuncDescription(output.name, arg_types_dict, 'Bool', None)


def main(spec_file_name,
         is_moore,
         dot_file_name,
         bounds,
         ltl2automaton_converter:LTL3BA,
         smt_solver):
    parse_spec = { 'py':parse_python_spec,
                  'ltl':parse_acacia_spec,
                  'cfg':parse_anzu_spec
                 }[spec_file_name.split('.')[-1]]
    input_signals, output_signals, ltl = parse_spec(spec_file_name)

    logger.info('LTL is:\n' + str(ltl))

    automaton = ltl2automaton_converter.convert(-ltl)

    logger.debug('automaton (dot) is:\n' + automaton2dot.to_dot(automaton))
    logger.debug(automaton)

    # TODO: use model_searcher instead
    tau_desc = _get_tau_desc(input_signals)

    desc_by_output = dict((o, _get_output_desc(o, not is_moore, input_signals))
                         for o in output_signals)

    encoder = SMTEncoder(UFLIA(None),
                         automaton,
                         smt_solver,
                         tau_desc,
                         input_signals, desc_by_output)
    model = model_searcher.search(bounds, encoder)

    is_realizable = model is not None

    logger.info(['unrealizable', 'realizable'][is_realizable])

    if is_realizable:
        dot_model = lts_to_dot(model, [ARG_MODEL_STATE], not is_moore)

        if not dot_file_name:
            logger.info(dot_model)
        else:
            write_out(dot_model, is_moore, 'dot', dot_file_name)

    return is_realizable


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Bounded Synthesis Tool')
    parser.add_argument('spec', metavar='spec', type=str,
                        help='the specification file (anzu, acacia+, or python format)')

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--moore', action='store_true', required=False,
                       help='treat the spec as Moore and produce Moore machine')
    group.add_argument('--mealy', action='store_false', required=False,
                       help='treat the spec as Mealy and produce Mealy machine')

    parser.add_argument('--dot', metavar='dot', type=str, required=False,
                        help='writes the output into a dot graph file')

    parser.add_argument('--log', metavar='log', type=str, required=False,
                        default=None,
                        help='name of the log file')

    group_bound = parser.add_mutually_exclusive_group()
    group_bound.add_argument('--bound', metavar='bound', type=int, default=128, required=False,
                             help='upper bound on the size of local process (default: %(default)i)')
    group_bound.add_argument('--size', metavar='size', type=int, default=0, required=False,
                             help='exact size of the process implementation(default: %(default)i)')

    parser.add_argument('--tmp', action='store_true', required=False, default=False,
                        help='keep temporary smt2 files')
    parser.add_argument('-v', '--verbose', action='count', default=0)

    args = parser.parse_args()

    logger = setup_logging(args.verbose, args.log)

    logger.info(args)

    with tempfile.NamedTemporaryFile(dir='./') as smt_file:
        smt_files_prefix = smt_file.name

    logic = UFLIA(None)
    ltl2ucw_converter, solver_factory = create_spec_converter_z3(logger, logic, False, smt_files_prefix)
    if not ltl2ucw_converter or not solver_factory:
        exit(1)

    bounds = list(range(1, args.bound + 1) if args.size == 0
                  else range(args.size, args.size + 1))

    is_realizable = main(args.ltl, args.moore, args.dot, bounds, ltl2ucw_converter, solver_factory.create())

    if not args.tmp:
        remove_files_prefixed(smt_files_prefix.split('/')[-1])

    exit(is_realizable)
