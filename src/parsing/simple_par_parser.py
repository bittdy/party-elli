from itertools import product, combinations
import math
from helpers.python_ext import bin_fixed_list
from translation2uct.ltl2automaton import get_solid_property


SCHED_ID_PREFIX = 'sch'

ACTIVE_NAME = 'active_'
SENDS_NAME, SENDS_PREV_NAME, HAS_TOK_NAME = 'sends_', 'prev_', 'tok_'


def concretize_anon_var(anon_var, process_index):
    assert not anon_var.endswith('_i')

    return anon_var[:-1]+ str(process_index)


def _instantiate_i(ltl_property, nof_processes):
    props_list = ['({0})'.format(ltl_property.replace('_i', str(i)))
                  for i in range(nof_processes)]
    new_prop = ' && '.join(props_list)

    return new_prop


def _instantiate_ii1(ltl_property, nof_processes):
    new_prop = ltl_property.replace('_i1', '1').replace('_i', '0')
    return new_prop


def _instantiate_ij(ltl_property, nof_processes):
#    props_list = ['({0})'.format(ltl_property.replace('_i', str(i)).replace('_j', str(j)))
#                  for i,j in combinations(range(nof_processes), 2)]
    props_list = ['({0})'.format(ltl_property.replace('_i', '0').replace('_j', str(j)))
                  for j in range(1, nof_processes)]
    new_prop = ' && '.join(props_list)
    return new_prop


def _instantiate_ii1j(ltl_property, nof_processes):
    props_list = ['({0})'.format(ltl_property.replace('_i1', '1').replace('_i', '0').replace('_j', str(j)))
                  for j in range(1, nof_processes)]
    new_prop = ' && '.join(props_list)
    return new_prop


def _get_spec_type(ltl_property):
    """ Return one of the spec type: 'i', 'i i+1', 'i j', 'i i+1 j' """

    assert '_i' in ltl_property, ltl_property

    type = 'i'
    if '_i1' in ltl_property:
        type += ' i+1'
    if '_j' in ltl_property:
        type += ' j'

    return type


def get_cutoff_size(prop):
    spec_type = _get_spec_type(prop)
    type_ = {'i': 2, 'i i+1': 3, 'i j': 4, 'i i+1 j': 5}[spec_type]
    return type_


def concretize_anon_vars(anon_vars, process_index):
    concretized_vars = [concretize_anon_var(i, process_index) for i in anon_vars]

    return concretized_vars


def anonymize_concr_var(concrete_variable):
    assert concrete_variable[-2] not in '1234567890', 'no support for > 9 processes'
    proc_index = int(concrete_variable[-1])

    anon_value = concrete_variable[:-1] + '_'

    return anon_value, proc_index


def parametrize_anon_var(var):
    assert var.endswith('_')
    return var+'i'


def anonymize_property(ltl_property, anon_vars):
    assert _get_spec_type(ltl_property) == 'i'

    prop = ltl_property
    for var in anon_vars:
        prop = prop.replace(parametrize_anon_var(var), var)

    return prop


#TODO: change input to expression!
def instantiate_formula(ltl_property, nof_processes):
    """ Works for the conjunction of properties only!
    """
    assert nof_processes > 0, str(nof_processes)

    if ltl_property == 'true':
        return 'true'

    handlers = {'i':_instantiate_i,
                'i i+1':_instantiate_ii1,
                'i j':_instantiate_ij,
                'i i+1 j':_instantiate_ii1j}

    spec_type = _get_spec_type(ltl_property)

    return handlers[spec_type](ltl_property, nof_processes)


def is_parametrized(ltl_spec):
    ltl_property = get_solid_property(ltl_spec.properties)
    return '_i' in ltl_property\
           or '_j' in ltl_property\
    or '_i1' in ltl_property


def get_inf_sched_prop(proc_index, nof_processes, sched_id_prefix):
    assert nof_processes > 0
    assert proc_index <= nof_processes - 1

    nof_sched_bits = int(max(math.ceil(math.log(nof_processes, 2)), 1))

    bits = [int(b) for b in bin_fixed_list(proc_index, nof_sched_bits)]

    id_as_formula = ' && '.join(['({0}{1}{2})'.format(['!', ''][bit_value], sched_id_prefix, bit_index)
                                 for bit_index, bit_value in enumerate(bits)])

    return 'GF({0})'.format(id_as_formula)


def get_fair_sched_prop(nof_processes, sched_id_prefix):
    sched_constraints = [get_inf_sched_prop(i, nof_processes, sched_id_prefix)
                         for i in range(nof_processes)]
    return ' && '.join(sched_constraints)


def get_tok_ring_par_io():
    return [SENDS_PREV_NAME], [SENDS_NAME, HAS_TOK_NAME]


#def get_par_tok_ring_safety_props():
#    tok_dont_disappear = 'G(({tok}i && !{sends}i) -> X{tok}i)'.format_map({'sends': SENDS_NAME,
#                                                                           'tok': HAS_TOK_NAME})
#    sends_with_token_only = "G({sends}i -> {tok}i)".format_map({'sends': SENDS_NAME,
#                                                                'tok': HAS_TOK_NAME})

    #TODO: can be specified with sends_prev
#    sends_means_release = "G(({active}i && {sends}i) -> X({tok}i1 && !{tok}i))".format_map({'sends': SENDS_NAME,
#                                                                                            'tok': HAS_TOK_NAME,
#                                                                                            'active': ACTIVE_NAME_PREFIX + '_'})
#    return [sends_means_release, sends_with_token_only, tok_dont_disappear]


def get_tok_rings_liveness_par_props():
    tok_rings_liveness_par_prop = "G({tok} -> F{sends})".format_map({'sends': parametrize_anon_var(SENDS_NAME),
                                                                     'tok': parametrize_anon_var(HAS_TOK_NAME)})
    return [tok_rings_liveness_par_prop]


def get_tok_rings_liveness_anon_props():
    tok_rings_liveness_par_prop = "G({tok} -> F{sends})".format_map({'sends': SENDS_NAME,
                                                                     'tok': HAS_TOK_NAME})
    return [tok_rings_liveness_par_prop]


#def get_tok_ring_concr_properties(nof_processes):
#    tok_rings_safety_par_props = get_par_tok_ring_safety_props()
#
#    par_safety_property = get_solid_property(tok_rings_safety_par_props)
#
#    concr_safety_property = concretize_property(par_safety_property, nof_processes)
#
#    #liveness, requires fair scheduling
#    tok_rings_liveness_par_props = get_tok_rings_liveness_par_props()
#    concr_finally_release_tok = concretize_property(tok_rings_liveness_par_props,
#        nof_processes)
#
#    return '({0}) && ({1})'.format(init_tok_distr, concr_safety_property), concr_finally_release_tok


def get_par_io(raw_ltl_spec):
    par_tok_ring_inputs, par_tok_ring_outputs = get_tok_ring_par_io()
    par_inputs = raw_ltl_spec.inputs + par_tok_ring_inputs
    par_outputs = raw_ltl_spec.outputs + par_tok_ring_outputs
    return par_inputs, par_outputs


def add_concretize_fair_sched(props, nof_processes):
    #init token distr is hardcoded into ParImpl

    fair_sched_prop = get_fair_sched_prop(nof_processes, SCHED_ID_PREFIX)
    concr_original_prop = instantiate_formula(get_solid_property(props), nof_processes)

    full_concr_prop = '({sched}) -> ({original})'.format_map(
            {'sched': fair_sched_prop,
             'original': concr_original_prop})

    return full_concr_prop


def is_local_property(property):
    return _get_spec_type(property) == 'i'