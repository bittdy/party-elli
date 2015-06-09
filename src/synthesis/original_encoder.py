import logging
from itertools import product
import sys
from nose.tools import assert_equal
from helpers.console_helpers import print_green, print_red

from helpers.labels_map import LabelsMap
from helpers.logging_helper import log_entrance
from helpers.python_ext import lmap
from interfaces.automata import Label, Automaton, LIVE_END, all_stimuli_that_satisfy, \
    get_next_states, Node, DEAD_END
from interfaces.lts import LTS
from interfaces.parser_expr import Signal
from interfaces.solver_interface import SolverInterface
from synthesis.func_description import FuncDescription
from synthesis.funcs_args_types_names import TYPE_MODEL_STATE, ARG_MODEL_STATE, ARG_S_a_STATE, ARG_S_g_STATE, \
    ARG_L_a_STATE, ARG_L_g_STATE, TYPE_S_a_STATE, TYPE_S_g_STATE, TYPE_L_a_STATE, TYPE_L_g_STATE, FUNC_REACH, FUNC_R, \
    smt_name_spec, smt_name_m, smt_name_free_arg, smt_arg_name_signal, smt_unname_if_signal, smt_unname_m, ARG_A_STATE, \
    TYPE_A_STATE
from synthesis.rejecting_states_finder import build_state_to_rejecting_scc


def _build_signals_values(signals, label) -> (dict, list):
    for s in signals:
        assert isinstance(s, Signal)

    value_by_signal = dict()
    free_values = []

    for s in signals:
        if s in label:
            value_by_signal[smt_arg_name_signal(s)] = str(label[s]).lower()
        else:
            value = '?{0}'.format(str(s)).lower()  # TODO: hack: we str(signal)
            value_by_signal[smt_arg_name_signal(s)] = value
            free_values.append(value)

    return value_by_signal, free_values


def assert_deterministic(s_a, s_g, l_a, l_g, lbl):
    assert_equal(len(get_next_states(s_a, lbl)), 1,  '\n' + str(get_next_states(s_a, lbl)) + '\n' + str(s_a) + '\n' + str(lbl))
    assert_equal(len(get_next_states(s_g, lbl)), 1,  '\n' + str(get_next_states(s_g, lbl)) + '\n' + str(s_g) + '\n' + str(lbl))
    assert_equal(len(get_next_states(l_a, lbl)), 1,  '\n' + str(get_next_states(l_a, lbl)) + '\n' + str(l_a) + '\n' + str(lbl))
    assert_equal(len(get_next_states(l_g, lbl)), 1,  '\n' + str(get_next_states(l_g, lbl)) + '\n' + str(l_g) + '\n' + str(lbl))


class OriginalEncoder:
    def __init__(self,
                 logic,
                 automaton:Automaton,
                 underlying_solver:SolverInterface,
                 tau_desc:FuncDescription,
                 inputs,
                 descr_by_output,
                 model_init_state:int):  # the automata alphabet is inputs+outputs
        self.logger = logging.getLogger(__name__)

        self.solver = underlying_solver
        self.logic = logic

        self.automaton = automaton

        self.inputs = inputs
        self.descr_by_output = descr_by_output
        self.tau_desc = tau_desc

        reach_args = {ARG_A_STATE: TYPE_A_STATE,
                      ARG_MODEL_STATE: TYPE_MODEL_STATE}

        r_args = reach_args

        self.reach_func_desc = FuncDescription(FUNC_REACH, reach_args, 'Bool', None)
        self.r_func_desc = FuncDescription(FUNC_R, r_args,
                                           logic.counters_type(sys.maxsize),
                                           None)

        #: :type: int
        self.model_init_state = model_init_state

        self.last_allowed_states = None

    def _smt_out(self, label:Label, smt_m:str, q:Node) -> str:
        conjuncts = []

        args_dict = self._build_args_dict(smt_m, label, q)

        for sig, val in label.items():
            if sig not in self.descr_by_output:
                continue

            out_desc = self.descr_by_output[sig]

            condition_on_out = self.solver.call_func(out_desc, args_dict)

            if val is False:
                condition_on_out = self.solver.op_not(condition_on_out)

            conjuncts.append(condition_on_out)

        condition = self.solver.op_and(conjuncts)
        return condition

    def _get_free_input_args(self, i_o:Label):
        _, free_args = _build_signals_values(self.inputs, i_o)
        return free_args

    def _build_args_dict(self, smt_m:str, i_o, q:Node) -> dict:
        args_dict = dict()
        args_dict[ARG_MODEL_STATE] = smt_m

        args_dict[ARG_A_STATE] = smt_name_spec(q, TYPE_A_STATE)

        if i_o is None:
            return args_dict

        smt_label_args, _ = _build_signals_values(self.inputs, i_o)
        args_dict.update(smt_label_args)
        return args_dict
    ##
    ##

    ## encoding headers
    def encode_headers(self, model_states):
        self._encode_automata_functions()
        self._encode_model_functions(model_states)
        self._encode_counters()

    def _encode_model_functions(self, model_states):
        self.solver.declare_enum(TYPE_MODEL_STATE, [smt_name_m(m) for m in model_states])
        self._define_declare_functions([self.tau_desc])
        self._define_declare_functions(self.descr_by_output.values())

    def _encode_automata_functions(self):
        self.solver.declare_enum(TYPE_A_STATE,
                                 map(lambda n: smt_name_spec(n, TYPE_A_STATE), self.automaton.nodes))

    def _encode_counters(self):
        self.solver.declare_fun(self.reach_func_desc)
        self.solver.declare_fun(self.r_func_desc)
    ##
    ##

    ## encoding rules
    def encode_initialization(self):
        for q, m in product(self.automaton.initial_nodes, [self.model_init_state]):
            vals_by_vars = self._build_args_dict(smt_name_m(m), None, q)

            self.solver.assert_(
                self.solver.call_func(
                    self.reach_func_desc, vals_by_vars))

    def encode_run_graph(self, states_to_encode):
        # state_to_rejecting_scc = build_state_to_rejecting_scc(impl.automaton)  # TODO: Does it help?

        # One option is to encode automata directly into SMT and have a query like:
        #
        # forall (s_a, s_a'), (s_g, s_g'), (l_a, l_a'), (l_g, l_g'), (m, m'), i_o:
        # (s_a, i_o, s_a') \in edge(S_a) &
        # (s_g, i_o, s_g') \in edge(S_g) &
        # (l_a, i_o, l_a') \in edge(L_a) &
        # (l_g, i_o, l_g') \in edge(L_g) &
        # (tau(m,i) = m') & out(m,i,other_args) = o &
        # reach(s_a,s_g,l_a,l_g,m)
        # ->
        # reach(s_a',s_g',l_a',l_g',m') & r(...) >< r(...)
        #
        # This requires Z3 to optimize a lot
        # (e.g., to understand that only valid automata transitions should be considered)
        # But the plus is that the query is _very_ compact.
        # I don't know if Z3 capable of doing such optimization.
        #
        # Thus, instead we will construct a query like:
        #
        # forall s_a, s_g, l_a, l_g, m, (i_o,s_a') in edges(s_a):
        # out(..) = o &
        # reach(s_a,..,m)
        # ->
        # reach(..) & r(..) >< r(..)
        #
        # We will explicitly enumerate all i_o for a given label (of the edge),
        # and compute s_g', l_a', l_g' depending on i_o.
        # We will handle the special case when s_g' is the rejecting state.

        state_to_rejecting_scc = build_state_to_rejecting_scc(self.automaton)

        for q in self.automaton.nodes:
            for m in states_to_encode:
                for label, dst_set_list in q.transitions.items():
                    self._encode_transitions(q, m, label,
                                             state_to_rejecting_scc)

            self.solver.comment('encoded spec state ' + smt_name_spec(q, TYPE_A_STATE))

    def _get_greater_op(self, q, is_rejecting,
                        q_next,
                        state_to_rejecting_scc):
        crt_rejecting_scc = state_to_rejecting_scc.get(q, None)
        next_rejecting_scc = state_to_rejecting_scc.get(q_next, None)

        if crt_rejecting_scc is not next_rejecting_scc:
            return None
        if crt_rejecting_scc is None:
            return None
        if next_rejecting_scc is None:
            return None

        return [self.solver.op_ge, self.solver.op_gt][is_rejecting]

    def _encode_transitions(self,
                            q:Node,
                            m,
                            i_o:Label,
                            state_to_rejecting_scc:dict):
        # syntax sugar
        smt_r = lambda args: self.solver.call_func(self.r_func_desc, args)
        smt_reach = lambda args: self.solver.call_func(self.reach_func_desc, args)
        #

        smt_m = smt_name_m(m)

        args_dict = self._build_args_dict(smt_m, i_o, q)
        free_input_args = self._get_free_input_args(i_o)

        smt_out = self._smt_out(i_o, smt_m, q)
        smt_pre = self.solver.op_and([smt_reach(args_dict), smt_out])

        #
        dst_set_list = q.transitions[i_o]
        assert len(dst_set_list) == 1, 'nondetermenistic transitions are not supported' + \
                                       str(dst_set_list) + '\n from ' + str(q) + \
                                       '\nwith io:' + str(i_o)
        dst_set = dst_set_list[0]

        #
        smt_m_next = self.solver.call_func(self.tau_desc, args_dict)

        smt_post_conjuncts = []
        for q_next, is_rejecting in dst_set:
            if q_next is DEAD_END or 'accept_all' in q_next.name:  # TODO: hack
                smt_post_conjuncts = [self.solver.false()]
                break

            args_dict_next = self._build_args_dict(smt_m_next, None, q_next)

            smt_post_conjuncts.append(smt_reach(args_dict_next))

            greater_op = self._get_greater_op(q, is_rejecting, q_next, state_to_rejecting_scc)

            if greater_op is not None:
                smt_post_conjuncts.append(greater_op(smt_r(args_dict_next),
                                                     smt_r(args_dict)))

        smt_post = self.solver.op_and(smt_post_conjuncts)
        pre_implies_post = self.solver.op_implies(smt_pre, smt_post)
        self.solver.assert_(
            self.solver.forall_bool(free_input_args,
                                    pre_implies_post))

    def encode_model_bound(self, allowed_model_states):
        self.solver.comment('encoding model bound: ' + str(allowed_model_states))

        # all args of tau function are quantified
        args_dict = dict((a, smt_name_free_arg(a))
                         for (a,ty) in self.tau_desc.inputs)

        free_vars = [(args_dict[a],ty)
                     for (a,ty) in self.tau_desc.inputs]

        smt_m_next = self.solver.call_func(self.tau_desc, args_dict)

        disjuncts = []
        for allowed_m in allowed_model_states:
            disjuncts.append(self.solver.op_eq(smt_m_next,
                                               smt_name_m(allowed_m)))

        condition = self.solver.forall(free_vars,
                                       self.solver.op_or(disjuncts))
        self.solver.assert_(condition)

        self.last_allowed_states = allowed_model_states
    ##
    ##

    def _define_declare_functions(self, func_descs):
        # should preserve the order: some functions may depend on others
        desc_by_name = dict((desc.name, (i, desc)) for (i, desc) in enumerate(func_descs))
        # TODO: cannot use set of func descriptions due to hack in FuncDescription

        unique_index_descs_sorted = sorted(desc_by_name.values(), key=lambda i_d: i_d[0])
        unique_descs = lmap(lambda i_d: i_d[1], unique_index_descs_sorted)

        for desc in unique_descs:
            if desc.definition is not None:
                self.solver.define_fun(desc)
            else:
                self.solver.declare_fun(desc)

    #
    #
    ###################### SMT Solver and Model Parser ###############################
    def push(self):
        return self.solver.push()

    def pop(self):
        return self.solver.pop()

    @log_entrance(logging.getLogger(), logging.INFO)
    def solve(self) -> LTS:
        self.solver.add_check_sat()

        self._encode_get_values()  # incremental solvers should not fail for such a strange case if UNSAT:)

        smt_lines = self.solver.solve()
        if not smt_lines:
            return None

        model = self._parse_sys_model(smt_lines)
        return model

    def _encode_get_values(self):
        func_descs = [self.tau_desc] + list(self.descr_by_output.values())

        for func_desc in func_descs:
            for input_dict in self._get_all_possible_inputs(func_desc):
                self.solver.get_value(self.solver.call_func(func_desc, input_dict))

    def _get_all_possible_inputs(self, func_desc:FuncDescription):
        arg_type_pairs = func_desc.inputs

        def get_values(t):
            return {          'Bool': ('true', 'false'),
                    TYPE_MODEL_STATE: [smt_name_m(m) for m in self.last_allowed_states],
                        TYPE_A_STATE: [smt_name_spec(s, TYPE_A_STATE) for s in self.automaton.nodes]
                   }[t]
        records = product(*[get_values(t) for (_,t) in arg_type_pairs])

        args = list(map(lambda a_t: a_t[0], arg_type_pairs))

        dicts = []
        for record in records:
            assert len(args) == len(record)

            arg_value_pairs = zip(args, record)
            dicts.append(dict(arg_value_pairs))

        return dicts

    @log_entrance(logging.getLogger(), logging.INFO)
    def _parse_sys_model(self, smt_get_value_lines):  # TODO: depends on SMT format
        output_models = dict()
        for output_sig, output_desc in self.descr_by_output.items():
            output_func_model = self._build_func_model_from_smt(smt_get_value_lines, output_desc)
            output_models[output_sig] = LabelsMap(output_func_model)

        tau_model = LabelsMap(self._build_func_model_from_smt(smt_get_value_lines, self.tau_desc))
        # tau_model = self._simplify_tau(tau_model, tau_func_desc, impl.states_by_process[0])

        lts = LTS([self.model_init_state],
                  output_models, tau_model,
                  ARG_MODEL_STATE,
                  self.inputs, list(self.descr_by_output.keys()))

        return lts

    def _build_func_model_from_smt(self, func_smt_lines, func_desc:FuncDescription) -> dict:
        """
        Return graph for the transition (or output) function: {label:output}.
        For label's keys are used:
        - for inputs/outputs: original signals
        - for states of automata and LTS: ARG_MODEL_STATE/ARG_S_a_STATE/etc.
        """
        func_model = {}
        signals = set(list(self.inputs) + list(self.descr_by_output.keys()))

        for l in func_smt_lines:
            #            (get-value ((tau t0 true true)))
            l = l.replace('get-value', '').replace('(', '').replace(')', '')
            tokens = l.split()
            if tokens[0] != func_desc.name:
                continue

            values = [self._parse_value(str_v)
                      for str_v in tokens[1:]]  # the very first - func_name
            smt_args = func_desc.get_args_dict(values[:-1])

            args = dict((smt_unname_if_signal(var,signals),val)
                        for var,val in smt_args.items())

            func_model[Label(args)] = values[-1]
        return func_model

    def _parse_value(self, str_v):
        if not hasattr(self, 'node_by_smt_value'):  # aka static method of the field
            self.node_by_smt_value = dict()
            self.node_by_smt_value.update((smt_name_spec(s, TYPE_A_STATE), s)
                                         for s in self.automaton.nodes)

        if str_v in self.node_by_smt_value:
            return self.node_by_smt_value[str_v]
        if str_v in ['false', 'true']:
            return str_v == 'true'
        return smt_unname_m(str_v)

    #
    #

    ############################### PARTIAL MODEL #################################
    def encode_model_solution(self, model:LTS, impl):  # TODO: no distributed case
        def to_bool(val:bool):
            return [self.solver.false(),
                    self.solver.true()][val]

        tau_model = impl.model_taus_descs[0]
        out_descs_dict = dict(map(lambda desc: (desc.name, desc), impl.outvar_desc_by_process[0].values()))

        for outvar_signal, labels_map in model.output_models.items():
            out_desc = out_descs_dict[outvar_signal]

            for args_dict, defined_bool_value in labels_map.items():
                defined_value = to_bool(defined_bool_value)

                computed_value = self.solver.call_func(out_desc, args_dict)

                condition = self.solver.op_eq(computed_value, defined_value)
                self.solver.assert_(condition)

        for args_dict, defined_next_state in model.tau_model.items():
            computed_next_state = self.solver.call_func(tau_model, args_dict)

            condition = self.solver.op_eq(computed_next_state, defined_next_state)
            self.solver.assert_(condition)

            # def _simplify_tau(self, tau_model:LabelsMap, tau_func_desc:FuncDescription, states) -> LabelsMap:
            #     tau_dict = dict()  # (t1,t2) -> labels
            #
            #     for (t1,t2) in product(states, repeat=2):
            #         labels = self._get_transitions(t1, t2, tau_model)
            #
            #         set_of_labels_wo_state = set()
            #         for lbl in labels:
            #             assert lbl['state'] == t2
            #
            #             lbl, _ = separate(lambda signal_value: signal_value[0] != 'state', lbl.items())
            #             set_of_labels_wo_state.add(lbl)
            #
            #         simplified_set = minimize_dnf_set(set_of_labels_wo_state)
            #         # notice that if the empty set then it is True
            #         tau_dict[(t1,t2)] = simplified_set
            #
            #     simplified_tau_model = LabelsMap()
            #     for ((t1,t2),labels) in tau_dict.items():
            #         for lbl in labels:
            #             # restore labels and add 'state'
            #             lbl['state'] = t1
            #             simplified_tau_model[lbl] = t2
            #
            #     return simplified_tau_model

            # def _get_transitions(self, t1, t2, tau_model:LabelsMap) -> Iterable:
            #     transitions = set()
            #     for (label,next_state) in tau_model.items():
            #         if label['state'] == t1 and next_state == t2:
            #             transitions.add(label)
            #     return transitions