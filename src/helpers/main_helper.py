import logging
from logging import FileHandler
import os
import sys
from synthesis.smt_logic import Logic
from synthesis.z3_via_files import Z3NonInteractiveViaFiles, FakeSolver
from synthesis.z3_via_pipe import Z3InteractiveViaPipes
from third_party.ansistrm import ColorizingStreamHandler
from automata_translations.ltl2automaton import LTL3BA


def get_root_dir() -> str:
    #make paths independent of current working directory
    rel_path = str(os.path.relpath(__file__))
    bosy_dir_toks = ['./'] + rel_path.split(os.sep)   # abspath returns 'windows' (not cygwin) path
    root_dir = ('/'.join(bosy_dir_toks[:-1]) + '/../../')   # root dir is two levels up compared to helpers/.
    return root_dir


def setup_logging(verbose_level:int=0, filename:str=None):
    level = None
    if verbose_level == -1:
        level = logging.CRITICAL
    if verbose_level is 0:
        level = logging.INFO
    elif verbose_level >= 1:
        level = logging.DEBUG

    formatter = logging.Formatter(fmt="%(asctime)-10s%(message)s", datefmt="%H:%M:%S")

    stdout_handler = ColorizingStreamHandler()
    stdout_handler.setFormatter(formatter)
    stdout_handler.stream = sys.stdout

    if not filename:
        filename = 'last.log'
    file_handler = FileHandler(filename=filename, mode='w')
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.addHandler(stdout_handler)
    root.addHandler(file_handler)

    root.setLevel(level)

    return logging.getLogger(__name__)


class Z3SolverFactory:
    def __init__(self, smt_tmp_files_prefix, z3_path, logic, logger,
                 is_incremental,
                 generate_queries_only,
                 remove_files):
        self.smt_tmp_files_prefix = smt_tmp_files_prefix
        self.z3_path = z3_path
        self.logic = logic
        self.logger = logger
        self.is_incremental = is_incremental
        self.generate_queries = generate_queries_only
        self.remove_files = remove_files
        assert not (self.is_incremental and self.generate_queries)

    def create(self, seed=''):
        if self.is_incremental:
            solver = Z3InteractiveViaPipes(self.logic, self.z3_path)
        elif self.generate_queries:
            solver = FakeSolver(self.smt_tmp_files_prefix+seed,
                                self.z3_path,
                                self.logic)
        else:
            solver = Z3NonInteractiveViaFiles(self.smt_tmp_files_prefix+seed,
                                              self.z3_path,
                                              self.logic,
                                              self.remove_files)

        return solver


def create_spec_converter_z3(logger:logging.Logger,
                             logic:Logic,
                             is_incremental:bool,
                             generate_queries_only:bool,
                             smt_tmp_files_prefix:str,
                             remove_tmp_files):
    """ Return ltl to automaton converter, Z3 solver """
    assert smt_tmp_files_prefix or is_incremental

    from config import z3_path, ltl3ba_path

    converter = LTL3BA(ltl3ba_path)
    solver_factory = Z3SolverFactory(smt_tmp_files_prefix, z3_path, logic, logger,
                                     is_incremental,
                                     generate_queries_only,
                                     remove_tmp_files)

    return converter, solver_factory
