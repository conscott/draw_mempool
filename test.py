#!/usr/bin/env python3

"""
Test transaction graph


             tx1                tx2
            / | \               /\
         tx3 tx4 tx5         tx6 tx7
                   \         /
                    \       /
                    tx8    tx9  tx12
                      \    / \  /
                       \  /   \/
                        tx10   tx11
"""
import draw_mempool
from decimal import Decimal

mempoolinfo = {
    '0001': {'fee': Decimal(0.00002000), 'size': 200, 'ancestorcount': 1, 'descendantcount': 6, 'time': 10, 'depends': [], 'spentby': ['0003', '0004', '0005']},
    '0002': {'fee': Decimal(0.00020000), 'size': 200, 'ancestorcount': 1, 'descendantcount': 6, 'time': 20, 'depends': [], 'spentby': ['0006', '0007']},
    '0003': {'fee': Decimal(0.00004000), 'size': 200, 'ancestorcount': 2, 'descendantcount': 1, 'time': 40, 'depends': ['0001'], 'spentby': []},
    '0004': {'fee': Decimal(0.00006000), 'size': 200, 'ancestorcount': 2, 'descendantcount': 1, 'time': 50, 'depends': ['0001'], 'spentby': []},
    '0005': {'fee': Decimal(0.00008000), 'size': 200, 'ancestorcount': 2, 'descendantcount': 3, 'time': 60, 'depends': ['0001'], 'spentby': ['0008']},
    '0006': {'fee': Decimal(0.00012000), 'size': 200, 'ancestorcount': 2, 'descendantcount': 4, 'time': 70, 'depends': ['0002'], 'spentby': ['0009']},
    '0007': {'fee': Decimal(0.00002000), 'size': 200, 'ancestorcount': 2, 'descendantcount': 1, 'time': 80, 'depends': ['0002'], 'spentby': []},
    '0008': {'fee': Decimal(0.00000210), 'size': 200, 'ancestorcount': 3, 'descendantcount': 2, 'time': 90, 'depends': ['0005'], 'spentby': ['0010']},
    '0009': {'fee': Decimal(0.00000210), 'size': 200, 'ancestorcount': 3, 'descendantcount': 3, 'time': 100, 'depends': ['0006'], 'spentby': ['0010', '0011']},
    '0010': {'fee': Decimal(0.00020000), 'size': 200, 'ancestorcount': 7, 'descendantcount': 1, 'time': 120, 'depends': ['0008', '0009'], 'spentby': []},
    '0011': {'fee': Decimal(0.00002000), 'size': 200, 'ancestorcount': 5, 'descendantcount': 1, 'time': 130, 'depends': ['0009', '0012'], 'spentby': []},
    '0012': {'fee': Decimal(0.00002000), 'size': 200, 'ancestorcount': 1, 'descendantcount': 2, 'time': 110, 'depends': [], 'spentby': ['0011']}
}


# Set mempool manually
draw_mempool.set_mempool(mempoolinfo)
# Add tx to graph
draw_mempool.add_to_graph('0008')
# Draw!
draw_mempool.draw_mempool_graph()

# Remove 'spentby' field and make sure everything still works
for tx in mempoolinfo:
    del mempoolinfo[tx]['spentby']

# Set mempool manually
draw_mempool.set_mempool(mempoolinfo)
# Add tx to graph
draw_mempool.add_to_graph('0008')
# Draw!
draw_mempool.draw_mempool_graph()
