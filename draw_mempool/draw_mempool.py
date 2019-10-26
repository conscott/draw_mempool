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
from matplotlib import pyplot as plt
from matplotlib.ticker import StrMethodFormatter
from networkx.drawing.nx_agraph import graphviz_layout
from draw_mempool.rpc import NodeCLI


# 1 BTC = COIN Satoshis
COIN = 100000000

# Max sequene
MAX_RBF_SEQUENCE = (0xffffffff-1)

# For looking at TX in blockchain.inf on double click
URL_SCHEME = "https://blockstream.info/tx/{}"

# Different depending on if #12479 is merged
build_tx_package_func = None

# Going to set later
rpc = None


# Set which function to use when building dependency graphs.
# New clients have PR #12479, and are more efficient
def set_build_tx_package_func(mempoolinfo):
    global build_tx_package_func
    randtx = next(iter(mempoolinfo.values()))
    if 'spentby' in randtx:
        # print("Using fast graph build function")
        build_tx_package_func = build_tx_package_pending
    else:
        # print("Using legacy graph build function")
        build_tx_package_func = build_tx_package_legacy


# Only needed if 'spentby' is not present
def find_descendants(mempoolinfo, tx, exclude=set()):
    return [child for (child, child_info) in mempoolinfo.items()
            if tx in child_info['depends'] and child not in exclude]


# Required if Tx does not have `spentby` in getrawmempool output
def build_tx_package_legacy(mempoolinfo, base_tx, G, seen):
    # Iterate through ancestors
    base_info = mempoolinfo[base_tx]
    anscestor = [tx for tx in base_info['depends'] if tx not in seen]
    for tx_ans in anscestor:
        # print("Adding ancestor edge %s -> %s, seen %s" % (tx_ans, base_tx, list(seen)))
        G.add_edge(tx_ans, base_tx)
        seen.add(tx_ans)
        build_tx_package_legacy(mempoolinfo, tx_ans, G, seen)
    if base_info['descendantcount'] > 1:
        for tx_desc in find_descendants(mempoolinfo, base_tx, exclude=seen):
            # print("Adding descendent edge %s -> %s" % (tx_ans, tx_desc))
            G.add_edge(base_tx, tx_desc)
            seen.add(tx_desc)
            build_tx_package_legacy(mempoolinfo, tx_desc, G, seen)


# Build a Tx graph the smart way - but requires PR #12479
def build_tx_package_pending(mempoolinfo, base_tx, G, seen):
    base_info = mempoolinfo[base_tx]
    anscestor = [tx for tx in base_info['depends'] if tx not in seen]
    for tx_ans in anscestor:
        G.add_edge(tx_ans, base_tx)
        seen.add(tx_ans)
        build_tx_package_pending(mempoolinfo, tx_ans, G, seen)

    descendants = [tx for tx in base_info['spentby'] if tx not in seen]
    for tx_desc in descendants:
        G.add_edge(base_tx, tx_desc)
        seen.add(tx_desc)
        build_tx_package_pending(mempoolinfo, tx_desc, G, seen)


# Signals RBF if any one of inputs has sequence number
# Less than 0xffffff-1
def signals_rbf(tx):
    for vin in rpc.getrawtransaction(tx, 'true')['vin']:
        if vin['sequence'] < MAX_RBF_SEQUENCE:
            return True
    return False


# Bip-125 replaceable if this tx or any of it's ancestors
# explicitly signal RBF
def is_replaceable(mempoolinfo, tx):

    if mempoolinfo[tx]['signals_rbf']:
        return True

    for parent in mempoolinfo[tx]['depends']:
        if is_replaceable(mempoolinfo, parent):
            return True

    return False


# Fee in Satoshis
def get_tx_fee(txinfo):
    return txinfo['fee']*COIN


# In Sat/Byte
def get_tx_feerate(txinfo):
    try:
        return float(txinfo['fee'])*COIN/txinfo['vsize']
    except KeyError:
        return float(txinfo['fee'])*COIN/txinfo['size']


# For CPFP - get previous ancestor stats excluding current transaction
def get_ancestor_feerate_minus_current(txinfo):
    try:
        return float((txinfo['ancestorfees'] - txinfo['fee'])*COIN) / (txinfo['ancestorsize'] - txinfo['vsize'])
    except KeyError:
        return float((txinfo['ancestorfees'] - txinfo['fee'])*COIN) / (txinfo['ancestorsize'] - txinfo['size'])


# The feerate for all ancestors  including this transaction
def get_ancestor_feerate(txinfo):
    return float(txinfo['ancestorfees']*COIN) / txinfo['ancestorsize']


# Going to add 1 to Tx age to avoid problems with log(time_delta) < 1
def get_tx_age_minutes(txinfo):
    return (time.time()-txinfo['time'])/60.0


# Make tx node size by fee
def fee_to_node_size(fee):
    return min(1+math.log(fee, 2)*10, 2000)


# Max tx node size by size in bytes
def tx_to_node_size(txinfo):
    return min(1+txinfo['vsize']/10.0, 20000000)


# Add a tx and all it's relatives to the graph
def add_to_graph(G, mempoolinfo, tx):
    G.add_node(tx)
    seen = set([tx])
    build_tx_package_func(mempoolinfo, tx, G, seen)
    return seen


# Draw just the transaction relations in nice spatial representation
def draw_txs_simple(G, mempoolinfo):
    # positions for all nodes
    pos = graphviz_layout(G, prog='dot')
    fees = [get_tx_feerate(mempoolinfo[tx]) for tx in G]
    nodesize = [tx_to_node_size(mempoolinfo[tx]) for tx in G]
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


# Animate!
def animate_graph(G, mempoolinfo, args, title=None):
    # First exec needs to show()
    plt.ion()
    fig, ax = plt.gcf(), plt.gca()
    draw_on_graph(G, mempoolinfo, args, ax, fig, title=title)
    ax.get_xaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
    ax.get_yaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
    plt.gca().invert_xaxis()
    plt.show()

    while True:
        plt.pause(.1)
        plt.clf()

        mempoolinfo = update_graph(G, mempoolinfo)

        draw_on_graph(G, mempoolinfo, args, ax, fig, title=title)
        ax.get_xaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
        ax.get_yaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
        plt.gca().invert_xaxis()
        fig.canvas.draw()
        plt.draw()


# Make nodes clickable. Have to find nearest neighbor to mouse
# and then make sure it's close enough to make sense
def setup_events(G, mempoolinfo, args, fig, ax):

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
            try:
                print("Size          : %s" % mempoolinfo[node]['vsize'])
            except KeyError:
                print("Size          : %s" % mempoolinfo[node]['size'])
            print("Fee           : %s" % mempoolinfo[node]['fee'])
            print("FeeRate       : %s" % get_tx_feerate(mempoolinfo[node]))
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
            for tx in get_bt_txs():
                if tx in G:
                    try:
                        G.remove_node(tx)
                    except Exception:
                        pass
            if not G:
                print("Mempool is empty without getblocktemplate")
            else:
                draw_mempool_graph(G,
                                   mempoolinfo,
                                   args,
                                   title='Mempool without getblocktemplate',
                                   preserve_scale=True)

    fig.canvas.mpl_connect('button_press_event', onClick)
    fig.canvas.mpl_connect('key_press_event', keyPress)


def setup_fig():
    fig, ax = plt.subplots(1)
    fig.set_size_inches(12, 8, forward=True)
    return fig, ax


def draw_mempool_graph(G, mempoolinfo, args, title=None, draw_labels=False, preserve_scale=False):

    if preserve_scale:
        old_ylim = plt.gca().get_ylim()
        old_xlim = plt.gca().get_xlim()

    fig, ax = setup_fig()

    setup_events(G, mempoolinfo, args, fig, ax)

    draw_on_graph(G, mempoolinfo, args, ax, fig, title=title, draw_labels=draw_labels)

    ax.get_xaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))
    ax.get_yaxis().set_major_formatter(StrMethodFormatter('{x:.1f}'))

    if preserve_scale:
        ax.set_ylim(old_ylim)
        ax.set_xlim(old_xlim)

    plt.gca().invert_xaxis()
    plt.show()


# Color nodes based on kind of tx (RBF, CPFP, etc.)
def get_nodecolors(G, mempoolinfo, args, plt):
    handles, rbf_txs, blocktemplatetxs, cpfp_txs = [], [], [], []
    highlight = args.hltxs if args.hltxs else []
    if args.color_rbf:
        rbf_txs = get_rbf_txs(G, mempoolinfo)
        green_patch = mpatches.Patch(color='green', label='bip125-replaceable Tx')
        handles.append(green_patch)
    if args.color_bt:
        blocktemplatetxs = get_bt_txs()
        blue_patch = mpatches.Patch(color='blue', label='getblocktemplate Tx')
        handles.append(blue_patch)
    if args.color_cpfp:
        cpfp_txs = get_cpfp_txs(mempoolinfo)
        cyan_patch = mpatches.Patch(color='cyan', label='CPFP Tx')
        handles.append(cyan_patch)
    if args.hltxs:
        yellow_patch = mpatches.Patch(color='yellow', label='Input Tx')
        handles.append(yellow_patch)

    nodecolors = ['b' if tx in blocktemplatetxs else
                  'c' if tx in cpfp_txs else
                  'g' if tx in rbf_txs else
                  'y' if tx in highlight else
                  'r' for tx in G]

    plt.legend(handles=handles)
    return nodecolors


def draw_on_graph(G, mempoolinfo, args, ax, fig, title=None, draw_labels=False):

    tx_fees = {tx: get_tx_feerate(mempoolinfo[tx]) for tx in G}
    min_fee, max_fee = min(tx_fees.values()), max(tx_fees.values())

    tx_ages = {tx: get_tx_age_minutes(mempoolinfo[tx]) for tx in G}
    min_age, max_age = min(tx_ages.values()), max(tx_ages.values())

    # Nodesize by tx size
    nodesize = [tx_to_node_size(mempoolinfo[tx]) for tx in G]

    # Lable as txid
    nodelabels = {tx: tx[:4] for tx in G}

    nodecolors = get_nodecolors(G, mempoolinfo, args, plt)

    # Can make the transparency of tx based on....?
    alpha = [0.2 if c == 'r' else 0.5 for c in nodecolors]

    # Going to make log scale, but need to correct
    if (max_age - min_age) > 100:

        for tx, age in tx_ages.items():
            if age < 1:
                tx_ages[tx] = 1.0

        plt.xscale('log')

    if max_fee < 5:
        plt.ylim(0.0, 5)
    elif (max_fee - min_fee) < 10:
        plt.ylim(0.0, max_fee + 5)
    elif (max_fee - min_fee) > 1000:
        plt.yscale('log')

    plt.title(title or "Transactions in mempool")
    plt.xlabel("Tx Age in Minutes")
    plt.ylabel("Fee in Sat per Byte")

    G.position = {tx: (tx_ages[tx], tx_fees[tx]) for tx in G}

    pos = G.position
    nx.draw_networkx_nodes(G, pos, alpha=alpha, node_color=nodecolors, node_size=nodesize, label='trans')
    nx.draw_networkx_edges(G, pos, alpha=0.15, arrowsize=15, label='spends')

    if draw_labels:
        nx.draw_networkx_labels(G, pos, labels=nodelabels, font_size=4)

    if args.nestimatefee:
        n = args.nestimatefee
        fee_estimates = {n: float(rpc.estimatesmartfee(n)['feerate'])*COIN/1000.0}
        for conf, fee in fee_estimates.items():
            plt.axhline(fee, color='k', linestyle='--')

    if args.lblock:
        plt.axvline(get_best_blocktime(), color='k', linestyle='--')

    ax.grid(True, alpha=0.5)


def get_best_blocktime():
    return (time.time()-rpc.getblock(rpc.getbestblockhash())['time'])/60.0


def tx_filter(tx_info,
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

    # For setting max relations it gets a little complicated
    max_related = min(maxancestors, maxdescendants)
    package_size = tx_info['ancestorcount'] + tx_info['descendantcount'] - 1

    try:
        tx_size = tx_info['vsize']
    except KeyError:
        tx_size = tx_info['size']

    return ((minfee <= tx_info['fee']*COIN <= maxfee) and
            (minfeerate <= get_tx_feerate(tx_info) <= maxfeerate) and
            (minancestors <= tx_info['ancestorcount']) and
            (mindescendants <= tx_info['descendantcount']) and
            (package_size <= max_related) and
            (minage <= get_tx_age_minutes(tx_info) <= maxage) and
            (minheight <= tx_info['height'] <= maxheight) and
            (minsize <= tx_size <= maxsize))


def make_mempool_graph(mempoolinfo, only_txs=None, txlimit=15000, **kwargs):

    G = nx.DiGraph()
    added = 0

    if only_txs:
        print("only adding %s" % only_txs)
        for tx in only_txs:
            seen = add_to_graph(G, mempoolinfo, tx)
            added += len(seen)
    else:
        mempoolinfo_cp = copy.deepcopy(mempoolinfo)
        while added < txlimit:
            try:
                tx = next(iter(mempoolinfo_cp))
            except StopIteration:
                break
            try:
                should_add = tx_filter(mempoolinfo[tx], **kwargs)
            except Exception:
                # Only breaks in test mode
                should_add = True
            if should_add:
                # Will pull in all related ancestor/descendant transcations
                seen = add_to_graph(G, mempoolinfo, tx)
                added += len(seen)
                # Remove these from our mempool copy so we don't duplicate
                for tx in seen:
                    mempoolinfo_cp.pop(tx, None)
            else:
                mempoolinfo_cp.pop(tx, None)

    print("Filtered down to %s txs" % len(G))
    return G if added else None


# Find eligible CPFP transactions
# This is not an exact science, just seeing if the
# new transaction makes the entire ancestor feerate
# jump up more than 10 sat/byte
def get_cpfp_txs(mempoolinfo):
    return [tx for tx, txinfo in mempoolinfo.items()
            if txinfo['ancestorcount'] > 1 and
            get_ancestor_feerate(txinfo) + 10.0 < get_ancestor_feerate_minus_current(txinfo)]


# Load RBF transactions
#
# Much faster if used with PR #12676
#
def get_rbf_txs(G, mempoolinfo):
    if 'bip125-replaceable' in next(iter(mempoolinfo.values())):
        print("Using new bip125-replaceable flag!")
        return set([tx for tx in G if mempoolinfo[tx]['bip125-replaceable']])
    else:
        print("WARNING! Calculating replace-by-fee txs is expensive!")
        rbf_txs = set()
        for tx in G:
            mempoolinfo[tx]['signals_rbf'] = signals_rbf(tx)
        for tx in G:
            if is_replaceable(mempoolinfo, tx):
                rbf_txs.add(tx)
        return rbf_txs


# Load block template transactions
def get_bt_txs():
    return set([tx['txid'] for tx in rpc.getblocktemplate(json.dumps({"rules": ["segwit"]}))['transactions']])


def test_bt():
    bt_args = {
        "capabilities": ["coinbasetxn", "workid", "coinbase/append"],
        "rules": ["segwit"]
    }
    txs = rpc.getblocktemplate(json.dumps(bt_args))['transactions']
    weight = sum([tx['weight'] for tx in txs])
    sigops = sum([tx['sigops'] for tx in txs])
    fee = sum([tx['fee'] for tx in txs])
    print("Got weight: %s | txs: %s | fees: %s | sigops: %s" % (weight, len(txs), fee, sigops))


def get_mempool():
    return rpc.getrawmempool('true')


def update_graph(G, old_mempool):

    old_set = set(old_mempool)
    mempoolinfo = get_mempool()
    new_set = set(mempoolinfo.keys())

    # Just add the tx differences to the graph
    added = new_set - old_set
    print("There are %s new Txs in mempool" % len(added))
    for tx in added:
        add_to_graph(G, mempoolinfo, tx)

    # And remove the old
    removed = old_set - new_set
    print("There are %s Txs removed from mempool" % len(removed))
    for tx in removed:
        try:
            G.remove_node(tx)
        except Exception:
            pass

    print("Size of mempool is %s txs" % len(mempoolinfo))
    return mempoolinfo


def main():
    # Parse arguments and pass through unrecognised args
    parser = argparse.ArgumentParser(add_help=True,
                                     usage='%(prog)s [options]',
                                     description='A tool to draw, filter, and animate mempool transactions',
                                     epilog='''Help text and arguments for individual test script:''',
                                     formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('--datadir', help='bitcoind data dir (if not default)')
    parser.add_argument('--animate', action='store_true', help='Update mempool drawing in real-time!')
    parser.add_argument('--lblock', action='store_true', help='Show time of last mined block')
    parser.add_argument('--nestimatefee', action='store', help='Show the fee estimate for n confirm')
    parser.add_argument('--color_bt', action='store_true', help='Color getblocktemplate txs different')
    parser.add_argument('--color_rbf', action='store_true', help='Color txs eligible for replace-by-fee different.')
    parser.add_argument('--color_cpfp', action='store_true', help='Color txs eligible for "Child Pays for Parent" (CPFP).')
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
    parser.add_argument('--minage', type=float, help='Min tx age in minutes')
    parser.add_argument('--maxage', type=float, help='Max tx age in minutes')
    parser.add_argument('--mindescendants', type=int, help='Min tx descendants')
    parser.add_argument('--maxdescendants', type=int, help='Max tx descendants')
    parser.add_argument('--minancestors', type=int, help='Min tx ancestors')
    parser.add_argument('--maxancestors', type=int, help='Max tx ancestors')
    args, unknown_args = parser.parse_known_args()

    if unknown_args:
        print("Unknown args: %s...Try" % unknown_args)
        print("./draw_mempool.py --help")
        sys.exit(0)

    # Min/max options
    filter_options = {k: v for k, v in args.__dict__.items() if v and ('min' in k or 'max' in k)}

    # Communicate with bitcoind like bitcoin test_framework
    global rpc
    rpc = NodeCLI(os.getenv("BITCOINCLI", "bitcoin-cli"), args.datadir)

    # Load mempool from rpc or snaphsot
    if args.snapshot:
        try:
            mempoolinfo = json.load(open(args.snapshot), parse_float=decimal.Decimal)
        except Exception as e:
            print("Error reading snapshot json: %s" % str(e))
            sys.exit(0)
    else:
        mempoolinfo = get_mempool()

    set_build_tx_package_func(mempoolinfo)
    try:
        G = make_mempool_graph(mempoolinfo, only_txs=args.hltxs, txlimit=args.txlimit, **filter_options)
        if not G:
            print("Filtered out all transactions, nothing to draw")
            sys.exit(0)
        if args.animate:
            animate_graph(G, mempoolinfo, args, title='Live Mempool!')
        else:
            draw_mempool_graph(G, mempoolinfo, args, title='Mempool')
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == '__main__':
    main()
