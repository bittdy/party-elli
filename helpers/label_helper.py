from typing import List, Iterable
from typing import Set

from helpers.expr_helper import get_sig_number
from helpers.expr_to_dnf import to_dnf_set
from helpers.python_ext import lmap
from interfaces.automaton import Label, LABEL_TRUE
from interfaces.expr import Expr, BinOp, Bool, Number
from interfaces.expr import Signal


def _has_common_label(label1:Label, label2:Label) -> bool:
    for k in label1:
        if k in label2 and label2[k] != label1[k]:
            return False
    return True


def common_label(label1:Label, label2:Label) -> Label or None:
    if not _has_common_label(label1, label2):
        return None

    new_dict = dict(label1)
    new_dict.update(label2)
    return Label(new_dict)


def negate_label(label:Label) -> Set[Label]:
    """empty set means label `false` here

    >>> negate_label(Label({Signal('g'):True})) \
        == {Label({Signal('g'):False})}
    True
    >>> negate_label(Label({Signal('g'):True, Signal('r'):True})) \
        == {Label({Signal('g'):False}), \
            Label({Signal('r'):False}) }
    True
    """

    if label == LABEL_TRUE:
        return set()
    # label==False is not possible

    lbl_e = label_to_expr(label)
    neg_lbl_e = ~lbl_e

    cubes = to_dnf_set(neg_lbl_e)  # type: List[List[Expr]]

    result = set()  # type: Set[Label]
    for cube in cubes:
        assert len(cube)
        neg_lbl = cube_expr_to_label(cube)
        result.add(neg_lbl)

    return result


def label_minus_labels(l:Label, labels:Iterable[Label]) -> List[Label]:
    e = labels_to_dnf_expr(labels)
    co_cubes = to_dnf_set(~e & label_to_expr(l))
    co_labels = lmap(cube_expr_to_label, co_cubes)
    return co_labels


def label_to_expr(label:Label) -> Expr:
    """ :param label: should not be 'False' """
    result = Bool(True)
    for k in label:
        atom = BinOp('=', k, Number(1))
        result &= atom if label[k] else ~atom
    return result


def labels_to_dnf_expr(labels:Iterable[Label]) -> Expr:
    e = Bool(False)
    for l in labels:
        e |= label_to_expr(l)
    return e


def cube_expr_to_label(cube:List[Expr]) -> Label:
    lbl = Label()
    for e in cube:
        assert e.name in '!=', str(e)
        if e.name == '!':
            sig, num = get_sig_number(e.arg)
            assert num == Number(1)
            lbl[sig] = False  # since e is negation
        else:
            sig, num = get_sig_number(e)
            assert num == Number(1)
            lbl[sig] = True

    return lbl
