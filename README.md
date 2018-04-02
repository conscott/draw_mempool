## Draw Mempool !

A tool to draw and inspect mempool transactions and their dependencies. This currently
requires a locally running version of bitcoind and will use `bitcoin-cli` to pull
for mempool and block template info.

This is a total WIP and may (probably) contain bugs.

![GitHub Logo](/imgs/mempool2.png)
![GitHub Logo](/imgs/mempool.png)

### Details

The program crawls the mempool building a graph of dependencies between transactions, i.e., unconfirmed transactions spending other unconfirmed transaction. This is represented in the graph as a line poiting from parent tx to child tx, where the child is spending some output of the parent. Such spending of unconfirmed outputs can lead to arbitrarily complex DAGs such as the sample below. 

![GitHub Logo](/imgs/txgraph.png)

In Bitcoin, these transaction graphs are considered "packages" and can be considered as a whole unit when deciding to include a trasaction into a block via `getblocktemplate`. This tool can be used to debug changes to `getblocktemplate`, inspect RBF and CPFP transactions, to evaluate fee estimates, or just explore tx dependencies. 

**NOTE** that when using any of the filter functions (like `--minfeerate`), the filter will be ignored if the transaction is part of a package (dependency graph), where another tx is above the `minfeerate`. For example, if tx1 pays 10 sat/byte and tx2 spends an output of tx1, with a feerate of 100 sat/byte, and `--minfeerate=20` is used, tx1 will still be show in the output drawing, in order to preserve dependency chain. 


### Installation Ubuntu & Debian

You need Python3  and can setup a local virtualenv:

```
sudo apt-get install virtualenv python3-dev python3-tk graphviz graphviz-dev
virtualenv -p /usr/bin/python3 .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Installion Mac / Windows
Submit a PR and tell me :)

### Try it out
```
source .venv/bin/activate
./draw_mempool.py --help
```

### Examples
```
# Only show transactions with ancestor dependencies
./draw_mempool.py --minancestors=2 --minfeerate=20 --maxage=60  

# Show high fee transactions
./draw_mempool.py --minfeerate=300

# Animate live mempool, coloring tx's to be included in next block as blue
./draw_mempool.py --maxage=10 --animate --color_bt

# Color RBF transactions differently
./draw_mempool.py --color_rbf 

# Draw the 2-block fee estimate as a horizontal line, as well as coloring 
# transactions to be included in the next block
./draw_mempool.py --nestimatefee=2 --color_bt
```

### Events
- Clicking on a tx will print the tx hash and fee / size information. 
- Double clicking on a transactions will open a browser tab, to inspect the tx on blockchain.info
- Clicking the 'm' button will redraw the mempool without the txs included in `getblocktemplate`, to help visualize what the mempool would look like after the next block is mined (can help with fee estimates). 
- You can zoom and pan using the buttons provided in the lower menu.

### TODO
- Calculate optimal blockfee based on mempool graph and compare to getblocktemplate

### Known Issues
- This program gets quite slow when there is a large mempool and does best when there are less than 10,000 transactions to draw. You can use the tx filter functions (like `--maxage`) to reduce the total txs drawn.
- When using `--animate`, the zoom will reset on every re-draw.
