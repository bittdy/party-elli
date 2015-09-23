from collections import defaultdict

from pygraph.algorithms.accessibility import mutual_accessibility
from pygraph.classes.digraph import digraph


def _convert_to_digraph(nodes):
    g = digraph()
    g.add_nodes(nodes)
    for n in nodes:
        for node_flag_pairs in n.transitions.values():
            for next_node, is_acc in node_flag_pairs:
                e = (n, next_node)
                if g.has_edge(e):
                    is_acc_new = is_acc or g.get_edge_properties(e)['is_acc']
                    g.set_edge_properties(e, is_acc=is_acc_new)
                else:
                    g.add_edge(e)
                    g.set_edge_properties(e, is_acc=is_acc)

    return g


def _build_edges_map(g) -> dict:
    edges = defaultdict(set)
    for e in g.edges():
        edges[e[0]].add(e[1])

    return edges


def find_rejecting_sccs(automaton):
    """
    :return: set of SCCs(set of nodes) that
             contains a rejecting transition between two nodes of the SCC.
    """

    g = _convert_to_digraph(automaton.nodes)
    sccs = mutual_accessibility(g)
    rejecting_sccs = set()
    dst_nodes_by_node = _build_edges_map(g)

    for scc in sccs.values():
        for n in scc:
            n_dst_nodes_within_scc = dst_nodes_by_node[n] & set(scc)
            if not n_dst_nodes_within_scc:
                continue

            is_acc = any(g.get_edge_properties((n, dst))['is_acc']
                         for dst in n_dst_nodes_within_scc)

            if is_acc:
                rejecting_sccs.add(frozenset(scc))

    return rejecting_sccs


def build_state_to_rejecting_scc(automaton):
    """ :return: dict node->SCC """
    rejecting_sccs = find_rejecting_sccs(automaton)

    state_to_rejecting_scc = dict()
    for scc in rejecting_sccs:
        for n in scc:
            state_to_rejecting_scc[n] = scc

    return state_to_rejecting_scc
