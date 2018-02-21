#!/usr/bin/env python3
import json
import getopt
import time
import copy
import math
import os
import sys
import networkx as nx
import subprocess
import decimal
from rpc import NodeCLI
from matplotlib import pyplot as plt
from matplotlib.ticker import ScalarFormatter, FormatStrFormatter, StrMethodFormatter
from networkx.drawing.nx_agraph import graphviz_layout

# Globals
rpc = NodeCLI(os.getenv("BITCOINCLI", "bitcoin-cli"))
G = nx.DiGraph()
mempoolinfo = {}
mempoolset = set()
blocktemplatetxs = set()
COIN = 100000000
URL_SCHEME = "https://blockchain.info/tx/{}"


# For testing
def set_mempool(mempool):
    mempoolinfo = mempool


def find_descendants(tx, exclude=set()):
    return [child for (child, child_info) in mempoolinfo.items()
            if tx in child_info['depends'] and child not in exclude]


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


# Build a Tx graph the smart way - but requires patch to bitcoin that is pending
def build_graph_pending(base_tx, G, seen):
    base_info = mempoolinfo[base_tx]
    anscestor = [tx for tx in base_info['depends'] if tx not in seen]
    for tx_ans in anscestor:
        G.add_edge(tx_ans, base_tx)
        seen.add(tx_ans)
        build_graph_pending(tx_ans, G, seen)

    descendants = [tx for tx in base_info['spentby'] if tx not in seen]
    for tx_desc in descendants:
        G.add_edge(base_tx, tx_desc)
        seen.add(tx_desc)
        build_graph_pending(tx_desc, G, seen)


def get_tx_fee(tx):
    return mempoolinfo[tx]['fee']*COIN


# In Sat/Byte
def get_tx_feerate(tx):
    return float(mempoolinfo[tx]['fee'])*COIN/mempoolinfo[tx]['size']
    # return float(mempoolinfo[tx]['ancestorfees'])*100000000.0/mempoolinfo[tx]['size']


# Going to add 1 to Tx age to avoid problems with log(time_delta) < 1
def get_tx_age_minutes(tx):
    return (time.time()-mempoolinfo[tx]['time'])/60.0+1.0


def fee_to_node_size(fee):
    return min(1+math.log(fee, 2)*10, 1000)


def tx_to_node_size(tx):
    return min(1+mempoolinfo[tx]['size']/10.0, 1000)


def add_to_graph(tx):
    G.add_node(tx)
    seen = set([tx])
    build_graph_pending(tx, G, seen)
    return seen


def draw_tx_simple():
    # positions for all nodes
    pos = graphviz_layout(G, prog='dot')
    fees = [get_tx_feerate(tx) for tx in G]
    nodesize = [tx_to_node_size(tx) for tx in G]
    nodecolors = [1 for f in fees]
    nx.draw_networkx_nodes(G, pos, node_color=nodecolors, node_size=nodesize, cmap=plt.cm.Reds_r)
    nx.draw_networkx_edges(G, pos, edgelist=G.edges(data=True), arrow_size=10, width=3)
    nx.draw_networkx_labels(G, pos, font_size=10, font_family='sans-serif')
    plt.axis('off')
    plt.show()


def follow_link(tx):
    url = URL_SCHEME.format(tx)
    cmd = "python -m webbrowser -t %s" % url
    FNULL = open(os.devnull, 'w')
    subprocess.call(cmd.split(), stdout=FNULL, stderr=subprocess.STDOUT)

def animate_graph(title=None):

    # First exec needs to show()
    plt.ion()
    fig, ax = setup_fig()
    setup_events(fig, ax)
    draw_on_graph(ax, fig, title=title)
    ax.get_xaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
    ax.get_yaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
    plt.gca().invert_xaxis()
    plt.show()

    while True:
        print("Redraw!")
        plt.pause(.1)
        plt.clf()
        diff = load_mempool(get_diff=True)
        for tx in diff:
            print("Adding %s to graph" % tx)
            add_to_graph(tx)
        draw_on_graph(ax, fig, title=title)
        ax.get_xaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
        ax.get_yaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
        plt.gca().invert_xaxis()
        fig.canvas.draw()
        plt.draw()

def setup_events(fig, ax):

    def getXRange():
        xmax, xmin = ax.get_xlim()
        return abs(xmax-xmin)

    def getYRange():
        ymax, ymin = ax.get_ylim()
        return abs(ymax-ymin)

    def getNodeForEvent(event):
        x, y = (event.xdata, event.ydata)
        if not x or not y:
            return None
        pos = G.position
        node, dist = min([(tx, ((pos[tx][0]-x)**2 + (pos[tx][1]-y)**2)**0.5) for tx in pos.keys()],
                         key=lambda tup: tup[1])
        nx, ny = pos[node]
        dist_ratio = max(abs(nx-x)/nx, abs(ny-y)/ny)
        if dist_ratio < .01:
            return node

    def onClick(event):
        if event.dblclick:
            node = getNodeForEvent(event)
            if node:
                follow_link(node)
        else:
            # Single click behavior
            pass

    fig.set_size_inches(12, 8, forward=True)
    fig.canvas.mpl_connect('button_press_event', onClick)


def setup_fig():
    fig, ax = plt.subplots(1)
    setup_events(fig, ax)
    return fig, ax


def draw_mempool_graph(title=None, draw_labels=False):
    fig, ax = setup_fig()
    draw_on_graph(ax, fig, title=title, draw_labels=draw_labels)
    ax.get_xaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
    ax.get_yaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
    plt.gca().invert_xaxis()
    plt.show()


def draw_on_graph(ax, fig, title=None, draw_labels=False):
    tx_fees = {tx: get_tx_feerate(tx) for tx in G}
    # tx_fees = {tx: get_tx_fee(tx) for tx in G}
    max_fee = max(tx_fees.values())
    min_fee = min(tx_fees.values())

    tx_ages = {tx: get_tx_age_minutes(tx) for tx in G}
    max_age = max(tx_ages.values())
    min_age = min(tx_ages.values())

    print("Max fee vs Min Fee: [%s, %s] = %s diff" % (max_fee, min_fee, max_fee-min_fee))
    print("Max Age vs Min Age: [%s, %s] = %s min " % (max_age, min_age, max_age-min_age))

    G.position = {tx: (tx_ages[tx], tx_fees[tx]) for tx in G}

    # Nodesize by fee-rate
    # nodesize = [fee_to_node_size(tx_fees[tx]) for tx in G]

    # Nodesize by tx size
    nodesize = [tx_to_node_size(tx) for tx in G]

    # Lable as txid
    nodelabels = {tx: tx[:4] for tx in G}

    # Node color has in or out of block template
    if blocktemplatetxs:
        nodecolors = ['b' if tx in blocktemplatetxs else 'r' for tx in G]
    else:
        nodecolors = ['r' for tx in G]

    # Can make the transparency of tx based on....?
    # alpha = [min(.2*mempoolinfo[tx]['ancestorcount'], 1) for tx in G]

    # Turn off log format for y-scale
    if (max_fee - min_fee) > 100:
        plt.yscale('log')

    if (max_age - min_age) > 100:
        plt.xscale('log')

    if max_fee < 5:
        plt.ylim(0.0, 5)

    # ax.autoscale(True)

    # plt.axis('off')
    plt.title(title or "Transactions in mempool")
    plt.xlabel("Tx Age in Minutes")
    plt.ylabel("Fee in Sat/Byte")

    pos = G.position
    nx.draw_networkx_nodes(G, pos, alpha=0.3, node_color=nodecolors, node_size=nodesize, label='trans')
    nx.draw_networkx_edges(G, pos, alpha=0.3, arrowsize=15, label='spends')

    if draw_labels:
        nx.draw_networkx_labels(G, pos, labels=nodelabels, font_size=4)


def tx_filter(tx,
              minfee=0.0, maxfee=21000000,
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
    return ((minfee <= tx_info['fee']*COIN <= maxfee) and
            (minfeerate <= get_tx_feerate(tx) <= maxfeerate) and
            (minancestors <= tx_info['ancestorcount'] <= maxancestors) and
            (mindescendants <= tx_info['descendantcount'] <= maxdescendants) and
            (minage <= get_tx_age_minutes(tx) <= maxage) and
            (minheight <= tx_info['height'] <= maxheight) and
            (minsize <= tx_info['size'] <= maxsize))


def make_mempool_graph(txlimit=10000, **kwargs):
    mempoolinfo_cp = copy.deepcopy(mempoolinfo)
    added = 0
    while added < txlimit:
        try:
            tx = next(iter(mempoolinfo_cp))
        except StopIteration:
            break
        if tx_filter(tx, **kwargs):
            # Will pull in all related ancestor/descendant transcations
            seen = add_to_graph(tx)
            added += len(seen)
            # Remove these from our mempool copy so we don't duplicate
            for tx in seen:
                mempoolinfo_cp.pop(tx, None)
        else:
            mempoolinfo_cp.pop(tx, None)
    return G if added else None


# Load block template transactions
def load_bt_txs():
    bt_weight = 0
    bt_fees = 0.0
    for tx in rpc.getblocktemplate()['transactions']:
        blocktemplatetxs.add(tx['txid'])
        bt_weight += tx['weight']
        bt_fees += tx['fee']
    print("Size of block template is %s txs" % len(blocktemplatetxs))
    print("Weight is %s and tx fees are %s" % (bt_weight, bt_fees/COIN))


# Load mempool transactions
def load_mempool(snapshot=None, get_diff=False):

    global mempoolset
    global mempoolinfo

    if get_diff:
        old_set = mempoolset

    if snapshot:
        mempoolinfo = json.load(open(snapshot), parse_float=decimal.Decimal)
    else:
        mempoolinfo = rpc.getrawmempool('true')

    mempoolset = set(mempoolinfo.keys())

    if blocktemplatetxs:
        diff = blocktemplatetxs-mempoolset
        # TODO - handle diff

    if get_diff:
        diff = mempoolset-old_set
        print("There are %s new Txs in mempool" % len(diff))
        removed = old_set-mempoolset
        print("There are %s Txs removed from mempool" % len(removed))
        for tx in removed:
            G.remove_node(tx)
        return diff

    print("Size of mempool is %s txs" % len(mempoolinfo))


def usage():
    print("""Draw and explore transactions in the mempool.\n
    ./draw_mempool.py [filter options]
          --colorbt                   Color getblocktemplate nodes different
          --snapshot=file.json        Specify json file of mempool snapshot
          --txs=[]                    Specify a particular tx id to draw
          --txlimit=COUNT             Max number of Tx (will stop filter once reached)
          --minfee=FEE                Min fee in satoshis
          --maxfee=FEE                Max fee in satoshis
          --minfeerate=FEERATE        Min fee in satoshis / byte
          --maxfeerate=FEERATE        Max fee in satoshis / byte
          --minheight=HEIGHT          Min block height
          --maxheight=HEIGHT          Max block height
          --minsize=SIZE              Min tx size in bytes
          --maxsize=SIZE              Max tx size in bytes
          --minage=SECONDS            Min tx age in seconds
          --maxage=SECONDS            Max tx age in seconds
          --mindescendants=COUNT      Minimum transactions decendants
          --maxdescendants=COUNT      Maximum transactions decendants
          --minancestors=COUNT        Minimum transaction ancestors
          --maxancestors=COUNT        Maximum transaction ancestors""")


def get_long_options():
    return ["minfee=", "maxfee=", "minfeerate=", "maxfeerate=",
            "minheight=", "maxheight=", "minsize=", "maxsize=",
            "minage=", "maxage=", "minancestors=", "maxancestors=",
            "mindescendant=s", "maxdescendants=",
            "txlimit=", "txs=",
            "snapshot=",
            "colorbt",
            "animate"]


def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], [], get_long_options())
    except getopt.GetoptError:
        usage()
        sys.exit(1)

    # Hacky is my name
    snapshot = None
    txs = None
    colorbt = False
    animate = False
    filter_options = {}
    for opt, arg in opts:
        if 'snapshot' in opt:
            snapshot = arg
        elif 'txs' in opt:
            txs = arg
        elif 'colorbt' in opt:
            colorbt = True
        elif 'animate' in opt:
            animate = True
        else:
            filter_options[opt.replace('-', '')] = int(arg)

    print("Using filters %s" % filter_options)

    # Load block template if passed in
    if colorbt:
        load_bt_txs()

    # Load mempool from rpc or snaphsot
    load_mempool(snapshot)

    # Draw individual transactions or entire mempool graph with filters
    if txs:
        for tx in txs.split(','):
            add_to_graph(tx)
            draw_mempool_graph()
    else:
        make_mempool_graph(**filter_options)
        if not G:
            print("Filtered out all transactions, nothing to draw")
        else:
            if animate:
                animate_graph(title='Live Mempool!')
            else:
                draw_mempool_graph(title='Mempool Filtered')

if __name__ == "__main__":
    main()
