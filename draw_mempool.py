#!/usr/bin/env python3
import getopt
import time
import copy
import math
import os
import sys
import networkx as nx
from rpc import NodeCLI
from matplotlib import pyplot as plt
from matplotlib.ticker import ScalarFormatter, FormatStrFormatter
from networkx.drawing.nx_agraph import graphviz_layout

mempoolinfo = {}
MIN_FEE = 1     # in Sat/Byte
HIGH_FEE = 100  # in Sat/Byte


def mempool_tx_filter(ans_count, desc_count):
    return [tx for tx, info in mempoolinfo.items()
            if info['ancestorcount'] > ans_count and info['descendantcount'] > desc_count]

def set_mempool(mempool):
    global mempoolinfo
    mempoolinfo = mempool

def find_descendants(tx, exclude=set()):
    return [child for (child, child_info) in mempoolinfo.items()
            if tx in child_info['depends'] and child not in exclude]

def build_graph_2(base_tx, G, seen):
    # Iterate through ancestors
    base_info = mempoolinfo[base_tx]
    anscestor = [tx for tx in base_info['depends'] if tx not in seen]
    for tx_ans in anscestor:
        G.add_edge(tx_ans, base_tx)
        seen.add(tx_ans)
        build_graph_2(tx_ans, G, seen)

    descendants = [tx for tx in base_info['spentby'] if tx not in seen]
    for tx_desc in descendants:
        # print("Adding descendent edge %s -> %s, seen %s" % (base_tx, tx_desc, list(seen)))
        G.add_edge(base_tx, tx_desc)
        seen.add(tx_desc)
        build_graph_2(tx_desc, G, seen)

def build_graph(base_tx, G, seen):
    # Iterate through ancestors
    base_info = mempoolinfo[base_tx]
    anscestor = [tx for tx in base_info['depends'] if tx not in seen]
    for tx_ans in anscestor:
        ans_info = mempoolinfo[tx_ans]
        # print("Adding ancestor edge %s -> %s, seen %s" % (tx_ans, base_tx, list(seen)))
        G.add_edge(tx_ans, base_tx)
        seen.add(tx_ans)
        build_graph(tx_ans, G, seen)
        if ans_info['descendantcount'] > 2:
            for tx_desc in find_descendants(tx_ans, exclude=seen):
                # print("Adding descendent edge %s -> %s" % (tx_ans, tx_desc))
                G.add_edge(tx_ans, tx_desc)
                seen.add(tx_desc)
                build_graph(tx_desc, G, seen)

# In Sat/Byte
def get_tx_fee(tx):
    return float(mempoolinfo[tx]['fee'])*100000000.0/mempoolinfo[tx]['size']
    # return float(mempoolinfo[tx]['ancestorfees'])*100000000.0/mempoolinfo[tx]['size']

def get_tx_age_minutes(tx):
    return (time.time()-mempoolinfo[tx]['time'])/60.0

def fee_to_node_size(fee):
    return min(1+math.log(fee, 2)*5, 1000)

def get_tx_graph(tx, draw=False):
    G = nx.DiGraph()
    G.add_node(tx)
    seen = set([tx])
    build_graph_2(tx, G, seen)
    if draw:
        draw_tx_simple(G)
    return G

def add_to_graph(G, tx):
    G.add_node(tx)
    seen = set([tx])
    build_graph_2(tx, G, seen)
    return seen

def draw_tx_simple(G):
    # positions for all nodes
    pos = graphviz_layout(G, prog='dot')
    fees = [get_tx_fee(tx) for tx in G]
    nodesize = [fee_to_node_size(f) for f in fees]
    nodecolors = [1 for f in fees]
    nx.draw_networkx_nodes(G, pos, node_color=nodecolors, node_size=nodesize, cmap=plt.cm.Reds_r)
    nx.draw_networkx_edges(G, pos, edgelist=G.edges(data=True), width=3)
    nx.draw_networkx_labels(G, pos, font_size=10, font_family='sans-serif')
    plt.axis('off')
    plt.show()

def draw_time_fee_tx(G, title=None):
    tx_fees = {tx: get_tx_fee(tx) for tx in G}
    max_fee = max(tx_fees.values())
    min_fee = min(tx_fees.values())

    tx_ages = {tx: get_tx_age_minutes(tx) for tx in G}
    max_age = max(tx_ages.values())
    min_age = min(tx_ages.values())

    print("Max fee vs Min Fee: [%s, %s] = %s diff" % (max_fee, min_fee, max_fee-min_fee))
    print("Max Age vs Min Age: [%s, %s] = %s min " % (max_age, min_age, max_age-min_age))

    G.position = {tx: (tx_ages[tx], tx_fees[tx]) for tx in G}
    nodesize = [fee_to_node_size(tx_fees[tx]) for tx in G]
    alpha = [min(.2*mempoolinfo[tx]['ancestorcount'], 1) for tx in G]

    fig, ax = plt.subplots()
    fig.set_size_inches(12, 8, forward=True)
    if max_fee > 100:
        plt.yscale('log')
        ax.get_yaxis().set_major_formatter(FormatStrFormatter('%.0f'))
        #ax.set_yticks([100, 300, 500, 750, 1000, 1200])

    if (max_age - min_age) > 100:
        plt.xscale('log')
        ax.get_xaxis().set_major_formatter(FormatStrFormatter('%.0f'))

    # plt.xlim(min_age-1, max_age+1)

    if max_fee < 5:
        plt.ylim(0.0, 5)

    # plt.axis('off')
    plt.title(title or "Transactions in mempool")
    plt.xlabel("Tx Age in Minutes")
    plt.ylabel("Fee in Sat/Byte")


    plt.gca().invert_xaxis()

    # nx.draw(G, G.position, with_labels=False)
    pos = G.position
    nx.draw_networkx_nodes(G, pos, alpha=alpha, node_size=nodesize)
    nx.draw_networkx_edges(G, pos, alpha=0.3)
    plt.show()

def high_ancestor(tx):
    return tx_filter(minfee_rate=1, minancestors=15)

def high_fee(tx):
    return tx_filter(minfeerate=HIGH_FEE)

def interesting(tx):
    return tx_filter(minfeerate=10, minancestors=4)

def tx_filter(tx, minfee=0.0, maxfee=21000000,
                  minfeerate=0, maxfeerate=21000000,
                  minancestors=1, maxancestors=26,
                  mindescendants=1, maxdescendants=26,
                  minage=0, maxage=315360000,
                  minheight=1, maxheight=21000000,
                  minsize=1, maxsize=8000000, **kwargs):

    if kwargs:
        print("You done fucked up!")
        print(kwargs)
        assert(False)

    tx_info = mempoolinfo[tx]
    return (minfee <= tx_info['fee'] <= maxfee and
            minfeerate <= get_tx_fee(tx) <= maxfeerate and
            minancestors <= tx_info['ancestorcount'] <= maxancestors and
            mindescendants <= tx_info['descendantcount'] <=  maxdescendants and
            minage <= get_tx_age_minutes(tx) <= maxage and
            minheight <= tx_info['height'] <=  maxheight and
            minsize <= tx_info['size'] <=  maxsize)


def get_mempool_graph(filter_func=tx_filter, txlimit=1000, **kwargs):
    G = nx.DiGraph()
    mempoolinfo_cp = copy.deepcopy(mempoolinfo)
    added = 0
    while added < txlimit:
        try:
            tx = next(iter(mempoolinfo_cp))
        except StopIteration:
            break
        if not filter_func or filter_func(tx, **kwargs):
            seen = add_to_graph(G, tx)
            added += len(seen)
            for tx in seen:
                mempoolinfo_cp.pop(tx, None)
        else:
            mempoolinfo_cp.pop(tx, None)
    return G if added else None


def usage():
    return "TODO"


if __name__ == "__main__":

    rpc = NodeCLI(os.getenv("BITCOINCLI", "bitcoin-cli"))

    # Get verbose mempoolinfo, TxId -> TxInfo
    mempoolinfo = rpc.getrawmempool('true')

    getopt_long_args = '''minfee= maxfee= minfeerate= maxfeerate=
                          minheight= maxheight= minsize= maxsize=
                          minage= maxage= minancestors= maxancestors=
                          mindescendants= maxdescendants= txlimits='''.split()

    filter_options = {}
    try:
        opts, args = getopt.getopt(sys.argv[1:], [], getopt_long_args)
    except getopt.GetoptError as err:
        usage()
        sys.exit(1)

    # Hacky is my name
    for opt, arg in opts:
        filter_options[opt.replace('-', '')] = int(arg)

    #print("Using filters %s" % filter_options)
    G = get_mempool_graph(**filter_options)
    if not G:
        print("Filtered out all transactions, nothing to draw")
    else:
        draw_time_fee_tx(G, title='Mempool Filtered')
