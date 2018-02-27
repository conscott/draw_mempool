#!/usr/bin/env python3
import argparse
import copy
import decimal
import json
import math
import networkx as nx
import os
import subprocess
import sys
import time
import matplotlib.patches as mpatches
from rpc import NodeCLI
from matplotlib import pyplot as plt
from matplotlib.ticker import ScalarFormatter, FormatStrFormatter, StrMethodFormatter
from networkx.drawing.nx_agraph import graphviz_layout
from statistics import median


# Globals #

# RPC interface
rpc = None
# The graph of all mempool transactions
G = nx.DiGraph()
# Tx -> TxInfo
mempoolinfo = {}
# set(Txs)
mempoolset = set()
# set(Txs) in getblocktemplate
blocktemplatetxs = set()
# set RBF txs
rbf_txs = set()
# for showing smart fee estimates
fee_estimates = {}
# For looking at TX in blockchain.inf on double click
URL_SCHEME = "https://blockchain.info/tx/{}"
# Hack until my #12479 is merged!
build_graph_func = None
# Highlight these
highlight = []
# 1 BTC = COIN Satoshis
COIN = 100000000
# Max sequene
MAX_SEQUENCE = (0xffffffff-1)


# For testing purposes
def set_mempool(mempool):
    global mempoolinfo
    mempoolinfo = mempool
    set_build_graph_func()


# Set which function to use when building graphs. This indirection
# Can be resolved if my PR adding child relations to getrawmempool output is
# being used in bitcoind
def set_build_graph_func():
    global build_graph_func
    randtx = next(iter(mempoolinfo.values()))
    if 'spentby' in randtx:
        build_graph_func = build_graph_pending
    else:
        build_graph_func = build_graph_legacy


# Only needed if 'spentby' is not present
def find_descendants(tx, exclude=set()):
    return [child for (child, child_info) in mempoolinfo.items()
            if tx in child_info['depends'] and child not in exclude]


# Required if Tx does not have `spentby` in getrawmempool output
def build_graph_legacy(base_tx, G, seen):
    # Iterate through ancestors
    base_info = mempoolinfo[base_tx]
    anscestor = [tx for tx in base_info['depends'] if tx not in seen]
    for tx_ans in anscestor:
        # print("Adding ancestor edge %s -> %s, seen %s" % (tx_ans, base_tx, list(seen)))
        G.add_edge(tx_ans, base_tx)
        seen.add(tx_ans)
        build_graph_legacy(tx_ans, G, seen)
    if base_info['descendantcount'] > 1:
        for tx_desc in find_descendants(base_tx, exclude=seen):
            # print("Adding descendent edge %s -> %s" % (tx_ans, tx_desc))
            G.add_edge(base_tx, tx_desc)
            seen.add(tx_desc)
            build_graph_legacy(tx_desc, G, seen)


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


# Check if tx is eligible for replace by fee
def is_rbf(tx):
    for vin in rpc.getrawtransaction(tx, 'true')['vin']:
        if vin['sequence'] < MAX_SEQUENCE:
            return True
    return False


# Fee in Satoshis
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
    return min(1+mempoolinfo[tx]['size']/10.0, 2000)


def add_to_graph(tx):
    G.add_node(tx)
    seen = set([tx])
    build_graph_func(tx, G, seen)
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


# Kick off a tab open after a double click near tx
def follow_link(tx):
    url = URL_SCHEME.format(tx)
    cmd = "python -m webbrowser -t %s" % url
    FNULL = open(os.devnull, 'w')
    subprocess.call(cmd.split(), stdout=FNULL, stderr=subprocess.STDOUT)


# Probably did not do this right
def animate_graph(title=None):
    # First exec needs to show()
    plt.ion()
    fig, ax = plt.gcf(), plt.gca()
    draw_on_graph(ax, fig, title=title)
    ax.get_xaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
    ax.get_yaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
    plt.gca().invert_xaxis()
    plt.show()

    while True:
        plt.pause(.1)
        plt.clf()

        load_mempool(update_diff=True)

        if blocktemplatetxs:
            load_bt_txs()

        draw_on_graph(ax, fig, title=title)
        ax.get_xaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
        ax.get_yaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
        plt.gca().invert_xaxis()
        fig.canvas.draw()
        plt.draw()


# Make nodes clickable. Have to find nearest neighbor to mouse
# and then make sure it's close enough to make sense
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
        if dist_ratio < .02:
            print("\nSelected Tx : %s" % node)
            print("Size          : %s" % mempoolinfo[node]['size'])
            print("Fee           : %s" % mempoolinfo[node]['fee'])
            print("FeeRate       : %s" % get_tx_feerate(node))
            return node

    def onClick(event):
        if event.dblclick:
            node = getNodeForEvent(event)
            if node:
                follow_link(node)
        else:
            # Single click behavior
            # Just print node info
            node = getNodeForEvent(event)

    def keyPress(event):
        # key press events!
        # m -> subtract getblocktemplate
        #
        if event.key == 'm':
            for tx in blocktemplatetxs:
                if tx in G:
                    try:
                        G.remove_node(tx)
                    except:
                        pass
            if not G:
                print("Mempool is empty without getblocktemplate")
            else:
                draw_mempool_graph(title='Mempool without getblocktemplate', preserve_scale=True)

    fig.canvas.mpl_connect('button_press_event', onClick)
    fig.canvas.mpl_connect('key_press_event', keyPress)


def setup_fig():
    fig, ax = plt.subplots(1)
    fig.set_size_inches(12, 8, forward=True)
    setup_events(fig, ax)
    return fig, ax


def draw_mempool_graph(title=None, draw_labels=False, preserve_scale=False):

    if preserve_scale:
        old_ylim = plt.gca().get_ylim()
        old_xlim = plt.gca().get_xlim()

    fig, ax = setup_fig()

    draw_on_graph(ax, fig, title=title, draw_labels=draw_labels)

    ax.get_xaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
    ax.get_yaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))

    if preserve_scale:
        ax.set_ylim(old_ylim)
        ax.set_xlim(old_xlim)

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

    G.position = {tx: (tx_ages[tx], tx_fees[tx]) for tx in G}

    # Nodesize by fee-rate
    # nodesize = [fee_to_node_size(tx_fees[tx]) for tx in G]

    # Nodesize by tx size
    nodesize = [tx_to_node_size(tx) for tx in G]

    # Lable as txid
    nodelabels = {tx: tx[:4] for tx in G}

    # If color-rbf

    # Node color has in or out of block template

    handles = []
    if rbf_txs:
        nodecolors = ['g' if tx in rbf_txs else 'r' for tx in G]
        green_patch = mpatches.Patch(color='green', label='Tx RBF Eligible')
        handles.append(green_patch)
    elif blocktemplatetxs:
        nodecolors = ['g' if tx in highlight else 'b' if tx in blocktemplatetxs else 'r' for tx in G]
        blue_patch = mpatches.Patch(color='blue', label='Tx in getblocktemplate')
        handles.append(blue_patch)
    else:
        nodecolors = ['g' if tx in highlight else 'r' for tx in G]
        if highlight:
            green_patch = mpatches.Patch(color='green', label='Input Tx')
            handles.append(green_patch)
    red_patch = mpatches.Patch(color='red', hatch='o', label='Tx')
    handles.append(red_patch)
    plt.legend(handles=handles)

    # Can make the transparency of tx based on....?
    alpha = [0.2 if c is 'r' else 0.4 for c in nodecolors]

    # Turn off log format for y-scale
    if (max_fee - min_fee) > 100:
        #plt.yscale('log')
        pass

    if (max_age - min_age) > 100:
        plt.xscale('log')

    if max_fee < 5:
        plt.ylim(0.0, 5)

    # plt.axis('off')
    plt.title(title or "Transactions in mempool")
    plt.xlabel("Tx Age in Minutes")
    plt.ylabel("Fee in Sat/Byte")

    pos = G.position
    nx.draw_networkx_nodes(G, pos, alpha=alpha, node_color=nodecolors, node_size=nodesize, label='trans')
    nx.draw_networkx_edges(G, pos, alpha=0.3, arrowsize=15, label='spends')

    if draw_labels:
        nx.draw_networkx_labels(G, pos, labels=nodelabels, font_size=4)

    if fee_estimates:
        for conf, fee in fee_estimates.items():
            plt.axhline(fee, color='k', linestyle='--')


def stats():
    # TODO
    mlen = len(mempoolinfo)
    tx_fees = [get_tx_feerate(tx) for tx in mempoolinfo]
    max_fee, min_fee, avg_fee, med_fee = max(tx_fees), min(tx_fees), sum(tx_fees)/len(tx_fees), median(tx_fees)
    tx_ages = [get_tx_age_minutes(tx) for tx in mempoolinfo]
    max_age, min_age, avg_age, med_age = max(tx_ages), min(tx_ages), sum(tx_ages)/len(tx_ages), median(tx_ages)
    tx_size = [tx_info['size'] for tx_info in mempoolinfo.values()]
    max_size, min_size, avg_size, med_size = max(tx_size), min(tx_size), sum(tx_size)/len(tx_size), median(tx_size)


def tx_filter(tx,
              minfee=0.0, maxfee=21000000,
              minfeerate=0, maxfeerate=21000000,
              minancestors=1, maxancestors=26,
              mindescendants=1, maxdescendants=26,
              minage=0, maxage=315360000,
              minheight=1, maxheight=21000000,
              minsize=1, maxsize=8000000, **kwargs):

    if kwargs:
        print("Unrecognized filters: %s" % kwargs)
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

    print("Filtered down to %s txs" % len(G))
    return G if added else None


# Load fee estimates
def load_fee_estimates(n):
    global fee_estimates
    fee_estimates = {n: float(rpc.estimatesmartfee(n)['feerate'])*COIN/1000.0}


# Load RBF transactions
#
# This is VERY SLOW and should be called with some set of
# filters that minimizes the total TX set
#
def load_rbf_txs():
    global rbf_txs
    rbf_txs.clear()

    for tx in G:
        if is_rbf(tx):
            rbf_txs.add(tx)


# Load block template transactions
def load_bt_txs():
    global blocktemplatetxs
    blocktemplatetxs.clear()
    bt_weight = 0
    bt_fees = 0.0

    # Need to include segwit txs in block template
    block_template_txs = rpc.getblocktemplate(json.dumps({"rules": ["segwit"]}))['transactions']

    for tx in block_template_txs:
        blocktemplatetxs.add(tx['txid'])



# Load mempool transactions
def load_mempool(snapshot=None, update_diff=False):

    global mempoolset
    global mempoolinfo

    if update_diff:
        old_set = mempoolset

    if snapshot:
        print("Using snapshot %s" % snapshot)
        mempoolinfo = json.load(open(snapshot), parse_float=decimal.Decimal)
    else:
        mempoolinfo = rpc.getrawmempool('true')

    mempoolset = set(mempoolinfo.keys())

    # This should be _okay_
    #
    # We only display mempoolinfo, so if we call getblocktemplate after getrawmempool
    # and there exists stuff in getblocktemplate that does not exists in mempool, it's
    # not drawn anyway and just means we are only drawing a subset of the valid block template
    """
    if blocktemplatetxs:
        pass
        diff = blocktemplatetxs-mempoolset
        if diff:
            print("Diff is %s" % len(diff))
    """

    # Remove old nodes from the graph
    if update_diff:
        diff = mempoolset-old_set
        print("There are %s new Txs in mempool" % len(diff))
        # Just add the tx differences to the graph
        for tx in diff:
            add_to_graph(tx)

        # And remove the old
        removed = old_set-mempoolset
        print("There are %s Txs removed from mempool" % len(removed))
        for tx in removed:
            try:
                G.remove_node(tx)
            except:
                pass

    print("Size of mempool is %s txs" % len(mempoolinfo))


def main():

    # Parse arguments and pass through unrecognised args
    parser = argparse.ArgumentParser(add_help=True,
                                     usage='%(prog)s [options]',
                                     description='A tool to draw, filter, and animate mempool transactions',
                                     epilog='''Help text and arguments for individual test script:''',
                                     formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('--stats', action='store_true', help='Get advanced mempool stats')
    parser.add_argument('--datadir', help='bitcoind data dir (if not default)')
    parser.add_argument('--animate', action='store_true', help='Update mempool drawing in real-time!')
    parser.add_argument('--nestimatefee', action='store', help='Show the fee estimate for n confirm')
    parser.add_argument('--colorbt', action='store_true', help='Color getblocktemplate txs different')
    parser.add_argument('--colorrbf', action='store_true', help='Color txs eligible for replace-by-fee different. VERY SLOW, Dont use with animate')
    parser.add_argument('--snapshot', help='Specify json file of mempool snapshot')
    parser.add_argument('--txs', action='append', help='Specific tx to draw, can list multiple')
    parser.add_argument('--hltxs', action='append', help='Specific transaction to highlight, can list multiple')
    parser.add_argument('--txlimit', type=int, default=10000, help=' Max number of Tx (will stop filter once reached)')
    parser.add_argument('--minfee', type=int, help='Min fee in satoshis')
    parser.add_argument('--maxfee', type=int, help='Max fee in satoshis')
    parser.add_argument('--minfeerate', type=float, help='Min fee rate in satoshis/byte')
    parser.add_argument('--maxfeerate', type=float, help='Max fee rate in satoshis/byte')
    parser.add_argument('--minheight', type=int, help='Min block height')
    parser.add_argument('--maxheight', type=int, help='Max block height')
    parser.add_argument('--minsize', type=int, help='Min tx size in bytes')
    parser.add_argument('--maxsize', type=int, help='Max tx size in bytes')
    parser.add_argument('--minage', type=float, help='Min tx age in seconds')
    parser.add_argument('--maxage', type=float, help='Max tx age in seconds')
    parser.add_argument('--mindescendants', type=int, help='Min tx descendants')
    parser.add_argument('--maxdescendants', type=int, help='Max tx descendants')
    parser.add_argument('--minancestors', type=int, help='Min tx ancestors')
    parser.add_argument('--maxancestors', type=int, help='Max tx ancestors')
    args, unknown_args = parser.parse_known_args()

    if unknown_args:
        print("Unknown args: %s...Try" % unknown_args)
        print("./draw_mempool.py --help")
        return

    # Min/max options
    filter_options = {k: v for k, v in args.__dict__.items() if v and ('min' in k or 'max' in k)}

    global rpc
    rpc = NodeCLI(os.getenv("BITCOINCLI", "bitcoin-cli"), args.datadir)

    global highlight
    if args.hltxs:
        highlight = args.hltxs

    global fee_estimates
    if args.nestimatefee:
        load_fee_estimates(args.nestimatefee)

    # Load mempool from rpc or snaphsot
    load_mempool(args.snapshot)

    if args.stats:
        stats()
        return

    # Load block template if passed in
    if args.colorbt:
        load_bt_txs()

    set_build_graph_func()
    setup_fig()

    try:
        # Draw individual transactions or entire mempool graph with filters
        if args.txs:
            for tx in args.txs:
                highlight.append(tx)
                add_to_graph(tx)
                draw_mempool_graph()
        else:
            make_mempool_graph(txlimit=args.txlimit, **filter_options)

            if not G:
                print("Filtered out all transactions, nothing to draw")
                return

            # Load rbf txs if passed in
            # Only look at ones in filtered mempool since operation is expensive
            if args.colorrbf:
                print("WARNING! Calculating replace-by-fee txs is expensive!")
                load_rbf_txs()

            if args.animate:
                animate_graph(title='Live Mempool!')
            else:
                draw_mempool_graph(title='Mempool Filtered')
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    main()
