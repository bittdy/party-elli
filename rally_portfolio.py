#!/usr/bin/env python3
from typing import List

from rally_kid_aiger import KidRealTask, KidUnrealTask
from rally_elli_bool import ElliBoolRealTask
from rally_elli_int import ElliIntRealTask
from syntcomp.rally_template import main_template
from syntcomp.task import Task
from syntcomp.task_creator import TaskCreator


# TODO:
# - last.log from many processes


if __name__ == "__main__":
    class PortfolioTasksCreator(TaskCreator):
        @staticmethod
        def create(ltl_text:str, part_text:str, is_moore:bool) -> List[Task]:
            return [
                KidRealTask('kid.real', ltl_text, part_text, is_moore, 4, 24),
                KidRealTask('kid.real.fo', ltl_text, part_text, is_moore, 4, 24, 2),
                ElliBoolRealTask('elli.bool.real.16', ltl_text, part_text, is_moore, 16, 16, 8),
                ElliIntRealTask('elli.int.real', ltl_text, part_text, is_moore, 1, 8),  # hangs on large
                KidUnrealTask('kid.unreal', ltl_text, part_text, is_moore, 2, 16, timeout=None),
            ]

    main_template("Portfolio",
                  PortfolioTasksCreator())
