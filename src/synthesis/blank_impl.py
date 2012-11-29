class BlankImpl:
    """ Blank implementation which does nothing but still can be fed to GenericEncoder """

    def __init__(self):
        self.state_var_name = 'state'

        self.automaton = None

        self.nof_processes = 0

        self.orig_inputs = ()

        self.init_states = ()
        self.aux_func_descs = ()

        self.outvar_desc_by_process = (()) # (((var, func_desc), (var, func_desc)), ((), ()), ..)

        self.taus_descs = ()
        self.model_taus_descs = ()

        self.states_by_process = ()
        self.state_types_by_process = ()


    def _get_state_name(self, state_type:str, state_number:int):
        return '{type_lower}{number}'.format(type_lower=state_type.lower(), number=str(state_number))


    def get_outputs_descs(self):
        result = []
        for proc_record in self.outvar_desc_by_process:
            proc_descs = []
            for var, desc in proc_record:
                proc_descs.append(desc)
            result.append(tuple(proc_descs))
        return tuple(result)

    def get_proc_tau_additional_args(self, proc_label, sys_state_vector, proc_index):
        return dict()

    def get_output_func_name(self, concr_var_name):
        return concr_var_name

    def filter_label_by_process(self, label, proc_index): #TODO: hack
        return label

    def get_free_sched_vars(self, label):
        return tuple()

    def get_architecture_trans_assumption(self, label, sys_state_vector):
        return ''

    def get_architecture_conditions(self):
        return tuple()

    def convert_global_args_to_local(self, arg_values_dict):
        """ global args dictionary has global names, local - local names """
        return arg_values_dict
